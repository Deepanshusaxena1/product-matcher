import pytest

from app.domain.models import Availability
from app.sources.amazon.page import is_robot_check, parse_amazon_page


def test_a_phone_page_yields_its_title_brand_breadcrumbs_and_spec_table(phone_html: str) -> None:
    page = parse_amazon_page(phone_html)

    assert page is not None
    assert page.title == "Samsung Galaxy S24 FE 5G AI Smartphone (Graphite, 8GB RAM, 128GB Storage)"
    assert page.brand == "Visit the Samsung Store"
    assert page.breadcrumbs == (
        "Electronics",
        "Mobiles & Accessories",
        "Smartphones & Basic Mobiles",
        "Smartphones",
    )
    assert page.spec("RAM Memory Installed") == "8 GB"
    assert page.spec("memory storage capacity") == "128 GB"  # labels are matched case-insensitively
    assert page.spec("Colour") == "Graphite"
    assert page.spec("Model Number") is None


def test_a_phone_page_yields_its_offer(phone_html: str) -> None:
    page = parse_amazon_page(phone_html)

    assert page is not None
    assert page.price_inr == 39999.0
    assert page.availability is Availability.IN_STOCK  # "Only 1 left in stock."
    assert page.image_url == "https://m.media-amazon.com/images/I/71eUNTW+nJL._SL1500_.jpg"
    assert len(page.bullets) == 5


def test_the_price_to_pay_is_read_never_the_struck_through_mrp() -> None:
    # Live layout of B0DDTHBCJP: the price-to-pay block's hidden text is empty, the M.R.P. comes next.
    html = (
        '<span id="productTitle">Puma Polo</span>'
        '<div id="corePriceDisplay_desktop_feature_div">'
        '<span class="a-price priceToPay apex-pricetopay-value"><span class="a-offscreen"></span>'
        '<span class="a-price-whole">759</span></span>'
        '<span class="a-price a-text-price apex-basisprice-value">'
        '<span class="a-offscreen">₹1,699</span></span>'
        "</div>"
        '<div id="corePrice_feature_div">'
        '<span class="a-price apex-pricetopay-value"><span class="a-offscreen">₹759.00</span></span></div>'
    )

    page = parse_amazon_page(html)

    assert page is not None
    assert page.price_inr == 759


def test_the_first_spec_with_a_label_wins(tv_html: str) -> None:
    # "Brand" is in the overview table before the detail tables repeat it as "Brand Name".
    page = parse_amazon_page(tv_html)

    assert page is not None
    assert page.spec("Brand") == "LG"
    assert page.spec("Model Number") == "43NU870BPLA"
    assert page.spec("Model Series") == "NU87 Series 2026"


def test_the_selected_variant_is_read_from_the_twister(tv_html: str, sneaker_html: str) -> None:
    tv, sneaker = parse_amazon_page(tv_html), parse_amazon_page(sneaker_html)

    assert tv is not None
    assert sneaker is not None
    assert tv.variation == {"display_size": "43 Inches", "set_name": "2026 Series"}
    assert sneaker.variation == {"color_name": "White", "size_name": "10 UK"}


def test_a_premium_brand_page_takes_the_brand_from_its_logo_link(sneaker_html: str) -> None:
    page = parse_amazon_page(sneaker_html)

    assert page is not None
    assert page.brand == "Visit the Nike Store"
    assert "DH2987-100" in page.description


def test_a_premium_page_without_a_store_link_takes_the_brand_from_its_trust_badge() -> None:
    # A layout Amazon serves for B0983NTYZ5 on some visits: logo without a store link, brand only in a badge.
    html = (
        '<span id="productTitle">Nike Mens Court Vision Lo NN Sneakers</span>'
        '<div id="productBrandLogo_feature_div">'
        '<a href="/premium/nike"><img alt="Authorised Seller"></a></div>'
        '<span class="offer-display-feature-text-message">'
        "<a href='/premium/nike?ref_=dp_psx_trustbadge_brand'>Nike</a></span>"
    )

    page = parse_amazon_page(html)

    assert page is not None
    assert page.brand == "Nike"


def test_detail_bullets_become_specs_without_their_direction_marks(polo_html: str) -> None:
    page = parse_amazon_page(polo_html)

    assert page is not None
    assert page.spec("Item model number") == "687093"
    assert page.spec("Department") == "Men"
    assert page.spec("Generic Name") == "T-Shirt"
    assert page.document_title == "Buy PUMA Men, ESS Logo Polo M, Black, M, (68709301) at Amazon.in"


@pytest.mark.parametrize(
    ("availability_html", "availability"),
    [
        ('<span class="a-color-success"> In stock </span>', Availability.IN_STOCK),
        ("<span> Only 2 left in stock - order soon. </span>", Availability.IN_STOCK),
        (
            "<span> Currently unavailable. We don't know when or if this item will be back. </span>",
            Availability.OUT_OF_STOCK,
        ),
        ("<span> Temporarily out of stock. </span>", Availability.OUT_OF_STOCK),
        ("<span> Usually dispatched in 3 to 4 weeks. </span>", Availability.UNKNOWN),
    ],
)
def test_the_availability_message_decides_stock(availability_html: str, availability: Availability) -> None:
    html = f'<span id="productTitle">Thing</span><div id="availability">{availability_html}</div>'

    page = parse_amazon_page(html)

    assert page is not None
    assert page.availability is availability


def test_a_page_without_a_product_title_is_not_a_product_page() -> None:
    assert parse_amazon_page("<html><body><h1>Page Not Found</h1></body></html>") is None


def test_amazons_robot_check_is_recognised(phone_html: str) -> None:
    captcha = (
        '<html><body><form method="get" action="/errors/validateCaptcha">'
        "<h4>Enter the characters you see below</h4></form></body></html>"
    )

    assert is_robot_check(captcha)
    assert not is_robot_check(phone_html)


def test_the_side_sheet_spec_table_is_read() -> None:
    # Newer layout (live page B09VSZNT7Z): the details sit in a side sheet, label in <th>, value in <td>.
    html = """
    <span id="productTitle">adidas Men Grand Court Base 2.0 Sportswear Shoes White 9</span>
    <div id="voyager-ns-desktop-side-sheet-main-section"><table>
      <tr><th>Model Name</th><td>Grand Court Base 2.0</td></tr>
      <tr><th>Manufacturer part number</th><td>GW9250</td></tr>
    </table></div>
    """

    page = parse_amazon_page(html)

    assert page is not None
    assert page.spec("Model Name") == "Grand Court Base 2.0"
    assert page.spec("Manufacturer part number") == "GW9250"
