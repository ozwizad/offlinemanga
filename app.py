from flask import Flask, request, jsonify, send_file, render_template_string
from flask_cors import CORS
import requests
from bs4 import BeautifulSoup
import re
from PIL import Image
from io import BytesIO
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader
import os
import tempfile
from urllib.parse import quote, urljoin
from concurrent.futures import ThreadPoolExecutor, as_completed

app = Flask(__name__)
CORS(app)

class MangaScraper:
    def __init__(self):
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        }
        self.session = requests.Session()
        self.session.headers.update(self.headers)
    
    def detect_site(self, url):
        if 'mangadex.org' in url:
            return 'mangadex'
        elif 'asura' in url:
            return 'asura'
        elif 'manganato' in url:
            return 'manganato'
        return 'generic'
    
    def scrape_mangadex(self, url):
        try:
            manga_id = re.search(r'title/([a-f0-9-]+)', url)
            if not manga_id:
                return None
            manga_id = manga_id.group(1)
            resp = requests.get(f'https://api.mangadex.org/manga/{manga_id}', timeout=10)
            titles = resp.json()['data']['attributes']['title']
            title = titles.get('en') or list(titles.values())[0]
            chapters = []
            offset = 0
            while True:
                api = f'https://api.mangadex.org/manga/{manga_id}/feed?translatedLanguage[]=en&order[chapter]=asc&limit=100&offset={offset}'
                data = requests.get(api, timeout=10).json()
                items = data.get('data', [])
                if not items:
                    break
                for item in items:
                    num = item['attributes'].get('chapter', 'N/A')
                    chapters.append({
                        'number': num,
                        'title': item['attributes'].get('title') or f'Chapter {num}',
                        'url': f'https://mangadex.org/chapter/{item["id"]}'
                    })
                if len(items) < 100:
                    break
                offset += 100
            return {'title': title, 'chapters': chapters}
        except Exception as e:
            print(f"MangaDex error: {e}")
            return None
    
    def scrape_manganato(self, url):
        try:
            print(f"Fetching: {url}")
            resp = self.session.get(url, timeout=15)
            soup = BeautifulSoup(resp.content, 'html.parser')
            
            title = 'Unknown Manga'
            for sel in ['h1', '.story-info-right h1']:
                elem = soup.select_one(sel)
                if elem:
                    title = elem.text.strip()
                    break
            print(f"Title: {title}")
            
            chapters = []
            for link in soup.find_all('a', href=True):
                href = link.get('href', '')
                text = link.text.strip()
                
                if '/chapter-' in href or '/chapter/' in href:
                    num_match = re.search(r'chapter[/-](\d+\.?\d*)', href, re.I)
                    if not num_match:
                        num_match = re.search(r'chapter\s*(\d+\.?\d*)', text, re.I)
                    
                    if num_match:
                        num = num_match.group(1)
                        if not href.startswith('http'):
                            href = urljoin(url, href)
                        chapters.append({
                            'number': num,
                            'title': text or f'Chapter {num}',
                            'url': href
                        })
            
            seen = set()
            unique = []
            for ch in chapters:
                if ch['url'] not in seen:
                    seen.add(ch['url'])
                    unique.append(ch)
            
            try:
                unique.sort(key=lambda x: float(x['number']))
            except:
                pass
            
            print(f"Found {len(unique)} chapters")
            return {'title': title, 'chapters': unique}
        except Exception as e:
            print(f"Manganato error: {e}")
            return None
    
    def scrape_asura(self, url):
        try:
            resp = requests.get(url, headers=self.headers, timeout=15)
            soup = BeautifulSoup(resp.content, 'html.parser')
            title = soup.select_one('h1')
            title = title.text.strip() if title else 'Unknown'
            chapters = []
            for link in soup.find_all('a', href=True):
                href = link.get('href', '')
                text = link.text.strip()
                if '/chapter/' in href.lower() or 'chapter' in text.lower():
                    num = re.search(r'chapter[:\s-]*(\d+)', text, re.I) or re.search(r'/chapter[/-](\d+)', href, re.I)
                    if num:
                        if not href.startswith('http'):
                            href = urljoin(url, href)
                        chapters.append({'number': num.group(1), 'title': text[:80], 'url': href})
            seen = set()
            unique = [c for c in chapters if c['url'] not in seen and not seen.add(c['url'])]
            try:
                unique.sort(key=lambda x: float(x['number']))
            except:
                pass
            return {'title': title, 'chapters': unique}
        except Exception as e:
            print(f"Asura error: {e}")
            return None
    
    def scrape_generic(self, url):
        return self.scrape_manganato(url)
    
    def get_chapter_images(self, url, site_type):
        try:
            if site_type == 'mangadex':
                chapter_id = re.search(r'chapter/([a-f0-9-]+)', url)
                if not chapter_id:
                    return []
                api = f'https://api.mangadex.org/at-home/server/{chapter_id.group(1)}'
                data = requests.get(api, timeout=10).json()
                base = data.get('baseUrl')
                ch = data.get('chapter', {})
                hash_val = ch.get('hash')
                files = ch.get('dataSaver', []) or ch.get('data', [])
                quality = 'data-saver' if ch.get('dataSaver') else 'data'
                if base and hash_val:
                    return [f'{base}/{quality}/{hash_val}/{f}' for f in files]
                return []
            
            print(f"Fetching chapter: {url}")
            resp = self.session.get(url, timeout=15)
            soup = BeautifulSoup(resp.content, 'html.parser')
            
            images = []
            container = soup.select_one('.container-chapter-reader') or soup
            
            for img in container.find_all('img'):
                src = img.get('src') or img.get('data-src')
                if not src:
                    continue
                if any(skip in src.lower() for skip in ['logo', 'icon', 'ad', 'banner', '.gif']):
                    continue
                if any(ext in src.lower() for ext in ['.jpg', '.jpeg', '.png', '.webp']):
                    if not src.startswith('http'):
                        src = urljoin(url, src)
                    images.append(src)
            
            images = list(dict.fromkeys(images))
            print(f"Found {len(images)} images")
            return images
        except Exception as e:
            print(f"Get images error: {e}")
            return []
    
    def download_image(self, img_url, referer):
        try:
            proxy = f"https://wsrv.nl/?url={quote(img_url, safe='')}&n=-1"
            r = requests.get(proxy, timeout=15)
            if r.status_code == 200 and len(r.content) > 500:
                return (img_url, r.content)
        except:
            pass
        try:
            r = requests.get(img_url, headers={'Referer': referer, 'User-Agent': self.headers['User-Agent']}, timeout=10)
            if r.status_code == 200 and len(r.content) > 500:
                return (img_url, r.content)
        except:
            pass
        return (img_url, None)
    
    def download_parallel(self, urls, referer, workers=6):
        results = {}
        with ThreadPoolExecutor(max_workers=workers) as ex:
            futures = {ex.submit(self.download_image, u, referer): u for u in urls}
            for f in as_completed(futures):
                url, data = f.result()
                if data:
                    results[url] = data
        return results


scraper = MangaScraper()

HTML_TEMPLATE = """<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Manga PDF Downloader</title>
<script src="https://cdn.tailwindcss.com"></script>
</head>
<body class="min-h-screen bg-gradient-to-br from-slate-900 via-purple-900 to-slate-900 text-white p-4">
<div class="max-w-2xl mx-auto">
<h1 class="text-3xl font-bold text-center mb-2 text-purple-400">MANGA DOWNLOADER</h1>
<p class="text-center text-gray-400 mb-6">Link yapistir - Chapter sec - PDF indir</p>

<div class="bg-slate-800 rounded-lg p-4 mb-4">
<div class="flex gap-2">
<input id="urlInput" type="text" placeholder="https://manganato.gg/manga/..." class="flex-1 bg-slate-700 border border-purple-500 rounded px-3 py-2 text-white">
<button id="scanBtn" class="px-4 py-2 bg-purple-600 hover:bg-purple-500 rounded font-bold">TARA</button>
</div>
<p class="text-xs text-gray-500 mt-2">Desteklenen: Manganato, MangaDex, Asura</p>
</div>

<div id="loading" class="hidden text-center py-8">
<div class="animate-spin h-8 w-8 border-2 border-purple-400 border-t-transparent rounded-full mx-auto mb-2"></div>
<p>Taraniyor...</p>
</div>

<div id="results" class="hidden bg-slate-800 rounded-lg p-4">
<div class="flex justify-between items-center mb-3">
<h2 id="mangaTitle" class="text-xl font-bold text-purple-300"></h2>
<button id="selectAllBtn" class="text-sm px-3 py-1 bg-purple-700 rounded">Tumunu Sec</button>
</div>
<div class="mb-3 flex gap-3 items-center">
<span>Secili: <strong id="selectedCount">0</strong></span>
<button id="downloadBtn" disabled class="px-4 py-2 bg-pink-600 disabled:opacity-40 rounded font-bold">INDIR</button>
</div>
<div id="chapterList" class="space-y-1 max-h-72 overflow-y-auto"></div>
</div>

<div id="progress" class="hidden bg-slate-800 rounded-lg p-4 mt-4 text-center">
<p class="font-bold mb-2">INDIRILIYOR...</p>
<p id="progressText" class="text-sm text-gray-400 mb-2"></p>
<div class="bg-slate-700 rounded-full h-2">
<div id="progressBar" class="h-full bg-purple-500 rounded-full" style="width: 0%"></div>
</div>
</div>
</div>

<script>
var chapters = [];
var selected = new Set();
var title = '';

document.getElementById('scanBtn').addEventListener('click', function() {
    var url = document.getElementById('urlInput').value.trim();
    if (!url) {
        alert('Link girin!');
        return;
    }
    
    document.getElementById('loading').classList.remove('hidden');
    document.getElementById('results').classList.add('hidden');
    
    fetch('/api/scrape', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({url: url})
    })
    .then(function(res) { return res.json(); })
    .then(function(data) {
        document.getElementById('loading').classList.add('hidden');
        if (data.error) {
            alert('Hata: ' + data.error);
            return;
        }
        if (!data.chapters || data.chapters.length === 0) {
            alert('Chapter bulunamadi!');
            return;
        }
        chapters = data.chapters;
        title = data.title;
        selected.clear();
        document.getElementById('mangaTitle').textContent = title;
        renderChapters();
        document.getElementById('results').classList.remove('hidden');
    })
    .catch(function(err) {
        document.getElementById('loading').classList.add('hidden');
        alert('Hata: ' + err.message);
    });
});

document.getElementById('selectAllBtn').addEventListener('click', function() {
    if (selected.size === chapters.length) {
        selected.clear();
    } else {
        for (var i = 0; i < chapters.length; i++) {
            selected.add(i);
        }
    }
    renderChapters();
});

document.getElementById('downloadBtn').addEventListener('click', function() {
    if (selected.size === 0) return;
    if (selected.size > 3) {
        if (!confirm('3ten fazla chapter secildi. Uzun surebilir. Devam?')) return;
    }
    
    var selectedChapters = [];
    selected.forEach(function(i) {
        selectedChapters.push(chapters[i]);
    });
    
    document.getElementById('results').classList.add('hidden');
    document.getElementById('progress').classList.remove('hidden');
    document.getElementById('progressText').textContent = 'PDF hazirlaniyor...';
    document.getElementById('progressBar').style.width = '30%';
    
    fetch('/api/download', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({chapters: selectedChapters, title: title})
    })
    .then(function(res) {
        if (!res.ok) {
            return res.json().then(function(e) { throw new Error(e.error); });
        }
        return res.blob();
    })
    .then(function(blob) {
        document.getElementById('progressBar').style.width = '100%';
        document.getElementById('progressText').textContent = 'Tamamlandi!';
        var a = document.createElement('a');
        a.href = URL.createObjectURL(blob);
        a.download = title.replace(/[^a-z0-9]/gi, '_') + '.pdf';
        a.click();
        setTimeout(function() {
            document.getElementById('progress').classList.add('hidden');
            document.getElementById('results').classList.remove('hidden');
        }, 1500);
    })
    .catch(function(err) {
        alert('Hata: ' + err.message);
        document.getElementById('progress').classList.add('hidden');
        document.getElementById('results').classList.remove('hidden');
    });
});

function renderChapters() {
    var container = document.getElementById('chapterList');
    container.innerHTML = '';
    
    for (var i = 0; i < chapters.length; i++) {
        var ch = chapters[i];
        var isSelected = selected.has(i);
        var div = document.createElement('div');
        div.className = 'p-2 rounded cursor-pointer border ' + (isSelected ? 'bg-purple-700 border-purple-400' : 'bg-slate-700 border-slate-600');
        div.setAttribute('data-index', i);
        div.innerHTML = '<span class="text-purple-300">Ch ' + ch.number + '</span> - ' + ch.title;
        div.addEventListener('click', function(e) {
            var idx = parseInt(this.getAttribute('data-index'));
            if (selected.has(idx)) {
                selected.delete(idx);
            } else {
                selected.add(idx);
            }
            renderChapters();
        });
        container.appendChild(div);
    }
    
    document.getElementById('selectedCount').textContent = selected.size;
    document.getElementById('downloadBtn').disabled = selected.size === 0;
}
</script>
</body>
</html>"""

@app.route('/')
def index():
    return render_template_string(HTML_TEMPLATE)

@app.route('/api/scrape', methods=['POST'])
def api_scrape():
    try:
        url = request.json.get('url', '')
        if not url:
            return jsonify({'error': 'URL gerekli'}), 400
        
        site = scraper.detect_site(url)
        print(f"Scraping {site}: {url}")
        
        if site == 'mangadex':
            r = scraper.scrape_mangadex(url)
        elif site == 'manganato':
            r = scraper.scrape_manganato(url)
        elif site == 'asura':
            r = scraper.scrape_asura(url)
        else:
            r = scraper.scrape_generic(url)
        
        if r and r.get('chapters'):
            print(f"Found {len(r['chapters'])} chapters")
            return jsonify(r)
        
        return jsonify({'error': 'Chapter bulunamadi'}), 404
    except Exception as e:
        print(f"Error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/download', methods=['POST'])
def api_download():
    try:
        data = request.json
        chapters = data.get('chapters', [])
        title = data.get('title', 'manga')
        
        if not chapters:
            return jsonify({'error': 'Chapter secilmedi'}), 400
        if len(chapters) > 5:
            return jsonify({'error': 'Max 5 chapter'}), 400
        
        print(f"Creating PDF: {title} ({len(chapters)} chapters)")
        site = scraper.detect_site(chapters[0].get('url', ''))
        
        pdf_path = os.path.join(tempfile.gettempdir(), f"manga_{abs(hash(title)) % 9999}.pdf")
        c = canvas.Canvas(pdf_path, pagesize=A4)
        w, h = A4
        
        c.setFont("Helvetica-Bold", 20)
        c.drawString(40, h - 80, title[:50])
        c.setFont("Helvetica", 12)
        c.drawString(40, h - 100, f"{len(chapters)} Chapter")
        c.showPage()
        
        total = 0
        for ch in chapters:
            print(f"Processing Ch {ch.get('number')}")
            c.setFont("Helvetica-Bold", 16)
            c.drawString(40, h - 80, f"Chapter {ch.get('number', '?')}")
            c.showPage()
            
            imgs = scraper.get_chapter_images(ch.get('url'), site)
            print(f"  Found {len(imgs)} images")
            
            if not imgs:
                continue
            
            downloaded = scraper.download_parallel(imgs, ch.get('url'), workers=6)
            print(f"  Downloaded {len(downloaded)} images")
            
            for url in imgs:
                if url not in downloaded:
                    continue
                try:
                    img = Image.open(BytesIO(downloaded[url]))
                    if img.size[0] < 100:
                        continue
                    if img.mode not in ('RGB', 'L'):
                        img = img.convert('RGB')
                    
                    ratio = img.size[1] / img.size[0]
                    pw, ph = w - 30, h - 30
                    if ratio > ph / pw:
                        nh = ph
                        nw = ph / ratio
                    else:
                        nw = pw
                        nh = pw * ratio
                    
                    buf = BytesIO()
                    img.save(buf, 'JPEG', quality=75)
                    buf.seek(0)
                    c.drawImage(ImageReader(buf), (w - nw) / 2, (h - nh) / 2, nw, nh)
                    c.showPage()
                    total += 1
                except:
                    pass
        
        c.save()
        print(f"PDF created: {total} pages")
        return send_file(pdf_path, as_attachment=True, download_name=f"{title[:25]}.pdf")
    except Exception as e:
        print(f"Error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/health')
def health():
    return jsonify({'status': 'ok'})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
