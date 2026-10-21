"""Public, paginated WatchStore inventory (not sold products or accessories)."""
import re
from urllib.parse import urljoin, urlparse, parse_qs

SITE = '名錶窩'
ROOT = 'https://www.watchstore.tw/'
STRAP_MARKER = '｜錶帶（內頁）：'


def parse_details(soup):
    """Read labelled specification cells, excluding menus and related products."""
    header = soup.find('img', src=re.compile(r'(?:^|/)iwatch_standard\.jpg$', re.I))
    table = header.find_next('table') if header else None
    if table is None:
        raise ValueError('WatchStore specification table missing')
    fields = {}
    for tr in table.find_all('tr'):
        cells = tr.find_all('td', recursive=False)
        for index in range(0, len(cells) - 1, 2):
            key = re.sub(r'\s+', '', cells[index].get_text('', strip=True)).rstrip('：:')
            if key not in ('錶帶', '錶況'):
                continue
            value = re.sub(r'\s+', ' ', cells[index + 1].get_text(' ', strip=True)).strip()
            if key in fields and fields[key] != value:
                raise ValueError('WatchStore conflicting specification: ' + key)
            fields[key] = value
    if not all(key in fields for key in ('錶帶', '錶況')):
        raise ValueError('WatchStore strap or condition label missing')
    return fields


def stored_strap(title):
    return title.rsplit(STRAP_MARKER, 1)[1] if STRAP_MARKER in title else None


def apply_details(item, fields):
    # Preserve the verbatim condition. The shared grader handles 9成5新/9成9新.
    title = item['title'].split(STRAP_MARKER, 1)[0]
    return dict(item, condition=fields['錶況'],
                title=title + STRAP_MARKER + (fields['錶帶'].replace('｜', '/') or '未提供'))


def product_url(raw, page_url):
    parsed = urlparse(urljoin(page_url, raw or ''))
    ids = parse_qs(parsed.query).get('prodnum', [])
    if (parsed.hostname != 'www.watchstore.tw' or parsed.path.lower() != '/prod_detail.asp'
            or len(ids) != 1 or not ids[0].isdigit()):
        return ''
    return ROOT + 'prod_detail.asp?prodnum=' + ids[0]


def pagination(soup, page_url):
    """Follow only the unfiltered active inventory, including hidden page ranges."""
    current = int(parse_qs(urlparse(page_url).query).get('page', ['1'])[0])
    last = current
    for anchor in soup.find_all('a', href=True):
        parsed = urlparse(urljoin(page_url, anchor['href']))
        query = parse_qs(parsed.query, keep_blank_values=True)
        pages = query.get('page', [])
        if (parsed.hostname != 'www.watchstore.tw' or parsed.path.lower() not in ('/', '/index.asp')
                or any(query.get(k, ['']) != [''] for k in ('keywords', 'larcode', 'newsclass'))
                or len(pages) != 1 or not pages[0].isdigit()):
            continue
        page = int(pages[0])
        if not 1 <= page <= 200:
            raise ValueError('WatchStore pagination exceeds safe page limit')
        last = max(last, page)
    return [ROOT + '?page=' + str(page) for page in range(2, last + 1)]


def parse_inventory(soup, page_url, brand_of, model_of):
    results = {}
    cards = set()
    for anchor in soup.find_all('a', href=True):
        link = product_url(anchor['href'], page_url)
        if not link or link in cards:
            continue
        card = None
        for parent in anchor.parents:
            if parent.name != 'table':
                continue
            links = {product_url(a['href'], page_url) for a in parent.find_all('a', href=True)} - {''}
            if links == {link} and re.search(r'價格\s*[:：]', parent.get_text(' ', strip=True)):
                card = parent
                break
        if card is None:
            raise ValueError('WatchStore product card missing price or structure: ' + link)
        cards.add(link)
        price_cell = next((td for td in card.find_all('td')
                           if re.match(r'^價格\s*[:：]', td.get_text(' ', strip=True))), None)
        if price_cell is None:
            raise ValueError('WatchStore product price cell missing: ' + link)
        price_text = price_cell.get_text(' ', strip=True)
        price_match = re.fullmatch(r'價格\s*[:：]\s*(?:NT\$|\$)\s*([\d,]+)\s*(?:元)?', price_text)
        price = int(price_match[1].replace(',', '')) if price_match else None
        if price is None and not re.search(r'面洽|洽詢|電洽|售出|售完', price_text):
            raise ValueError('WatchStore unrecognized price: ' + link)
        # Description is inside the inner table. Keep inline word fragments joined.
        descriptions = price_cell.find_parent('table').find_all('p')
        text = ' '.join(p.get_text(' ', strip=True) for p in descriptions)
        if not text:
            text = card.get_text(' ', strip=True).split(price_text, 1)[0]
        text = re.split(r'歡迎來[店電]手錶置換', text, maxsplit=1)[0].strip()
        # The site sometimes splits reference suffixes with a space.
        text = re.sub(r'(?<!\d)(\d{6})\s+(CHNR|GRNR|BLNR|BLRO|TBR|LN|LV|LB)\b', r'\1\2', text, flags=re.I)
        compact = re.sub(r'\s+', '', text)
        brand, model = brand_of(text), model_of(text)
        if brand == '其他':
            continue
        if re.search(r'紙袋|提袋|攜帶盒|攜行袋|收納袋|保護袋|原廠錶盒|鑰匙圈|擦拭布|貼膜完成|貼完一顆錶|貼膜服務|錶帶專賣|全新原廠錶帶|維修服務|項鍊|戒指|耳環|外套', compact):
            continue
        if re.search(r'已售出|已售完', compact + price_text):
            continue
        year = re.search(r'(20\d{2})年(?:新式|木紋|電子)*(?:保單|保卡|保證書)', compact)
        condition = re.search(r'未使用品|全新品|全新|9[.．]9成新|二手美品|中古美品|二手|中古|媲美新品|\d(?:[.．]\d)?成新', compact)
        image = ''
        for img in card.find_all('img'):
            parsed = urlparse(urljoin(page_url, img.get('data-src') or img.get('src') or ''))
            if parsed.hostname == 'www.watchstore.tw' and parsed.path.lower().startswith('/product/'):
                image = parsed._replace(scheme='https').geturl()
                break
        results[link] = dict(site=SITE, url=link, title=text, brand=brand, model=model,
                             year=year[1] if year else '', condition=condition[0] if condition else '',
                             price=price, price_text=str(price) if price is not None else '洽詢', image_url=image)
    if not cards:
        raise ValueError('WatchStore inventory has no product cards; retain previous inventory')
    return list(results.values())
