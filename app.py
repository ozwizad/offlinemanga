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
import time
import os
import tempfile
from urllib.parse import quote, urljoin, urlparse

app = Flask(__name__)
CORS(app)

class MangaScraper:
    def __init__(self):
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
        }
        self.session = requests.Session()
        self.session.headers.update(self.headers)
    
    def detect_site(self, url):
        if 'mangadex.org' in url:
            return 'mangadex'
        elif 'asuracomic' in url or 'asura' in url:
            return 'asura'
        elif 'manganato' in url or 'chapmanganato' in url or 'manganato.gg' in url:
            return 'manganato'
        return 'generic'
    
    def scrape_mangadex(self, url):
        try:
            manga_id = re.search(r'title/([a-f0-9-]+)', url)
            if not manga_id:
                return None
            manga_id = manga_id.group(1)
            manga_response = requests.get(f'https://api.mangadex.org/manga/{manga_id}')
            manga_data = manga_response.json()
            titles = manga_data['data']['attributes']['title']
            title = titles.get('en') or titles.get('ja-ro') or list(titles.values())[0] if titles else 'Unknown'
            all_chapters = []
            offset = 0
            while True:
                api_url = f'https://api.mangadex.org/manga/{manga_id}/feed?translatedLanguage[]=en&order[chapter]=asc&limit=100&offset={offset}'
                response = requests.get(api_url)
                data = response.json()
                items = data.get('data', [])
                if not items:
                    break
                for item in items:
                    attrs = item['attributes']
                    chapter_num = attrs.get('chapter', 'N/A')
                    chapter_title = attrs.get('title') or f'Chapter {chapter_num}'
                    all_chapters.append({
                        'number': chapter_num,
                        'title': chapter_title,
                        'url': f'https://mangadex.org/chapter/{item["id"]}',
                        'id': item['id']
                    })
                if len(items) < 100:
                    break
                offset += 100
                time.sleep(0.3)
            return {'title': title, 'chapters': all_chapters}
        except Exception as e:
            print(f"MangaDex error: {e}")
            return None
    
    def scrape_manganato(self, url):
        try:
            print(f"Scraping Manganato: {url}")
            response = self.session.get(url, timeout=15)
            soup = BeautifulSoup(response.content, 'html.parser')
            title = 'Unknown Manga'
            title_elem = soup.select_one('.story-info-right h1') or soup.select_one('h1')
            if title_elem:
                title = title_elem.text.strip()
            chapters = []
            chapter_list = soup.select('.row-content-chapter li') or soup.select('.chapter-list .row')
            for item in chapter_list:
                link = item.select_one('a')
                if link:
                    chapter_url = link.get('href')
                    chapter_text = link.text.strip()
                    num_match = re.search(r'chapter[:\s-]*(\d+\.?\d*)', chapter_text, re.I)
                    chapter_num = num_match.group(1) if num_match else 'N/A'
                    chapters.append({'number': chapter_num, 'title': chapter_text, 'url': chapter_url})
            try:
                chapters.sort(key=lambda x: float(x['number']))
            except:
                pass
            return {'title': title, 'chapters': chapters}
        except Exception as e:
            print(f"Manganato error: {e}")
            return None
    
    def scrape_asura(self, url):
        try:
            print(f"Scraping Asura: {url}")
            session = requests.Session()
            session.headers.update(self.headers)
            session.headers['Referer'] = 'https://asuracomic.net/'
            time.sleep(2)
            response = session.get(url, timeout=20)
            if response.status_code != 200:
                return None
            soup = BeautifulSoup(response.content, 'html.parser')
            title = 'Unknown Manga'
            for selector in ['h1', 'h2', 'h3']:
                elems = soup.select(selector)
                for elem in elems:
                    text = elem.text.strip()
                    if len(text) > 3 and len(text) < 100 and 'chapter' not in text.lower():
                        title = text
                        break
                if title != 'Unknown Manga':
                    break
            chapters = []
            for link in soup.find_all('a', href=True):
                href = link.get('href', '')
                text = link.text.strip()
                if '/chapter/' in href.lower() or 'chapter' in text.lower():
                    num = None
                    for match in [re.search(r'chapter[:\s-]*(\d+\.?\d*)', text, re.I), re.search(r'/chapter[/-](\d+)', href, re.I)]:
                        if match:
                            num = match.group(1)
                            break
                    if num:
                        if not href.startswith('http'):
                            href = urljoin(url, href)
                        chapters.append({'number': num, 'title': text[:100] or f'Chapter {num}', 'url': href})
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
            return {'title': title, 'chapters': unique}
        except Exception as e:
            print(f"Asura error: {e}")
            return None
    
    def scrape_generic(self, url):
        try:
            response = self.session.get(url, timeout=15)
            soup = BeautifulSoup(response.content, 'html.parser')
            title = 'Unknown Manga'
            for selector in ['h1', 'h2', '.manga-title']:
                elem = soup.select_one(selector)
                if elem and len(elem.text.strip()) > 3:
                    title = elem.text.strip()
                    break
            chapters = []
            for link in soup.find_all('a', href=True):
                href = link.get('href', '')
                text = link.text.strip()
                if '/chapter/' in href.lower() or 'chapter' in text.lower():
                    num_match = re.search(r'(\d+\.?\d*)', text) or re.search(r'chapter[/-]?(\d+)', href, re.I)
                    if num_match:
                        if not href.startswith('http'):
                            href = urljoin(url, href)
                        chapters.append({'number': num_match.group(1), 'title': text[:100] or f'Chapter {num_match.group(1)}', 'url': href})
            seen = set()
            unique = [ch for ch in chapters if ch['url'] not in seen and not seen.add(ch['url'])]
            try:
                unique.sort(key=lambda x: float(x['number']))
            except:
                pass
            return {'title': title, 'chapters': unique}
        except Exception as e:
            print(f"Generic error: {e}")
            return None
    
    def get_chapter_images(self, chapter_url, site_type='generic'):
        try:
            if site_type == 'mangadex':
                return self._get_mangadex_images(chapter_url)
            response = self.session.get(chapter_url, timeout=15)
            soup = BeautifulSoup(response.content, 'html.parser')
            images = []
            container = soup.select_one('.container-chapter-reader') or soup.select_one('.reading-content') or soup
            for img in container.find_all('img'):
                src = img.get('src') or img.get('data-src') or img.get('data-lazy-src')
                if not src:
                    continue
                skip = ['logo', 'icon', 'avatar', 'banner', 'ad', 'facebook', 'twitter', '.gif']
                if any(s in src.lower() for s in skip):
                    continue
                if not any(ext in src.lower() for ext in ['.jpg', '.jpeg', '.png', '.webp']):
                    continue
                if not src.startswith('http'):
                    src = urljoin(chapter_url, src)
                images.append(src)
            return list(dict.fromkeys(images))
        except Exception as e:
            print(f"Get images error: {e}")
            return []
    
    def _get_mangadex_images(self, chapter_url):
        try:
            chapter_id = re.search(r'chapter/([a-f0-9-]+)', chapter_url)
            if not chapter_id:
                return []
            api_url = f'https://api.mangadex.org/at-home/server/{chapter_id.group(1)}'
            response = requests.get(api_url, timeout=15)
            if response.status_code != 200:
                return []
            data = response.json()
            base_url = data.get('baseUrl')
            chapter_data = data.get('chapter', {})
            chapter_hash = chapter_data.get('hash')
            if not base_url or not chapter_hash:
                return []
            image_files = chapter_data.get('data', []) or chapter_data.get('dataSaver', [])
            quality = 'data' if chapter_data.get('data') else 'data-saver'
            return [f'{base_url}/{quality}/{chapter_hash}/{f}' for f in image_files]
        except Exception as e:
            print(f"MangaDex images error: {e}")
            return []
    
    def download_image_with_proxy(self, img_url, referer_url, site_type='generic'):
        # Method 1: Direct
        try:
            headers = {'User-Agent': self.headers['User-Agent'], 'Referer': referer_url, 'Accept': 'image/*'}
            resp = requests.get(img_url, headers=headers, timeout=15)
            if resp.status_code == 200 and len(resp.content) > 1000:
                return resp.content
        except:
            pass
        
        # Method 2: wsrv.nl proxy
        try:
            proxy_url = f"https://wsrv.nl/?url={quote(img_url, safe='')}"
            resp = requests.get(proxy_url, timeout=20)
            if resp.status_code == 200 and len(resp.content) > 1000:
                return resp.content
        except:
            pass
        
        # Method 3: images.weserv.nl
        try:
            proxy_url = f"https://images.weserv.nl/?url={quote(img_url, safe='')}&output=jpg"
            resp = requests.get(proxy_url, timeout=20)
            if resp.status_code == 200 and len(resp.content) > 1000:
                return resp.content
        except:
            pass
        
        # Method 4: allorigins
        try:
            proxy_url = f"https://api.allorigins.win/raw?url={quote(img_url, safe='')}"
            resp = requests.get(proxy_url, timeout=20)
            if resp.status_code == 200 and len(resp.content) > 1000:
                return resp.content
        except:
            pass
        
        return None


scraper = MangaScraper()

HTML_TEMPLATE = '''
<!DOCTYPE html>
<html lang="tr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Manga Downloader</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <style>
        @keyframes shimmer { 0% { background-position: 0% 50%; } 100% { background-position: 200% 50%; } }
        .shimmer-text { background: linear-gradient(to right, #a855f7, #ec4899, #a855f7); -webkit-background-clip: text; -webkit-text-fill-color: transparent; background-size: 200% auto; animation: shimmer 3s linear infinite; }
    </style>
</head>
<body class="min-h-screen bg-gradient-to-br from-slate-950 via-purple-950 to-slate-900 text-white">
    <div class="container mx-auto px-4 py-8 max-w-4xl">
        <div class="text-center mb-12">
            <h1 class="text-5xl font-black mb-3 shimmer-text">MANGA DOWNLOADER</h1>
            <p class="text-purple-300">> Link yapıştır → Chapter seç → İndir_</p>
        </div>
        <div class="bg-slate-900/50 border border-purple-500/30 rounded-2xl p-6 mb-6">
            <div class="flex gap-3">
                <input type="text" id="mangaUrl" placeholder="https://manganato.gg/manga/..." class="flex-1 bg-slate-950 border-2 border-purple-500/50 rounded-xl px-4 py-3 text-white">
                <button onclick="scrape()" class="px-6 py-3 bg-gradient-to-r from-purple-600 to-pink-600 rounded-xl font-bold">TARA</button>
            </div>
            <div class="text-xs text-purple-400/70 mt-2">
                ✓ Manganato, MangaDex, Asura Scans | 💡 Max 3 chapter (proxy kullanılıyor)
            </div>
        </div>
        <div id="loading" class="hidden text-center py-16">
            <div class="animate-spin rounded-full h-12 w-12 border-b-2 border-purple-400 mx-auto mb-4"></div>
            <p class="text-purple-300">Analiz ediliyor...</p>
        </div>
        <div id="results" class="hidden bg-slate-900/50 border border-purple-500/30 rounded-2xl p-6">
            <div class="flex justify-between items-center mb-4">
                <h2 id="mangaTitle" class="text-2xl font-bold"></h2>
                <button onclick="selectAll()" class="px-4 py-2 bg-purple-600/30 border border-purple-400/50 rounded-lg text-sm">Tümünü Seç</button>
            </div>
            <div class="mb-4 flex gap-2 items-center">
                <span class="text-purple-300">Seçilen: <span id="selectedCount">0</span></span>
                <button onclick="downloadPDF()" id="downloadBtn" disabled class="px-6 py-2 bg-gradient-to-r from-pink-600 to-purple-600 disabled:opacity-50 rounded-lg font-bold">📥 PDF İNDİR</button>
            </div>
            <div id="chapters" class="space-y-2 max-h-96 overflow-y-auto"></div>
        </div>
        <div id="downloadProgress" class="hidden bg-slate-900/50 border border-purple-500/30 rounded-2xl p-6 mt-6">
            <div class="text-center mb-4">
                <div class="text-xl font-bold mb-2">İNDİRİLİYOR...</div>
                <div id="progressText" class="text-purple-300 text-sm"></div>
            </div>
            <div class="w-full bg-slate-800 rounded-full h-3">
                <div id="progressBar" class="h-full bg-gradient-to-r from-purple-600 to-pink-600 rounded-full" style="width: 0%"></div>
            </div>
        </div>
    </div>
    <script>
        let allChapters = [], selectedChapters = new Set(), mangaTitle = '';
        async function scrape() {
            const url = document.getElementById('mangaUrl').value.trim();
            if (!url) return alert('Link girin!');
            document.getElementById('loading').classList.remove('hidden');
            document.getElementById('results').classList.add('hidden');
            try {
                const res = await fetch('/api/scrape', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({url})});
                const data = await res.json();
                if (!res.ok || !data.chapters?.length) throw new Error(data.error || 'Chapter bulunamadı');
                allChapters = data.chapters; mangaTitle = data.title; selectedChapters.clear();
                document.getElementById('mangaTitle').textContent = mangaTitle;
                displayChapters();
                document.getElementById('loading').classList.add('hidden');
                document.getElementById('results').classList.remove('hidden');
            } catch (err) { document.getElementById('loading').classList.add('hidden'); alert('Hata: ' + err.message); }
        }
        function displayChapters() {
            const c = document.getElementById('chapters'); c.innerHTML = '';
            allChapters.forEach((ch, i) => {
                const sel = selectedChapters.has(i);
                const div = document.createElement('div');
                div.className = `p-3 rounded-lg cursor-pointer border-2 ${sel ? 'bg-purple-600/30 border-purple-400' : 'bg-slate-800/50 border-slate-700/50'}`;
                div.onclick = () => { sel ? selectedChapters.delete(i) : selectedChapters.add(i); displayChapters(); };
                div.innerHTML = `<div class="flex items-center gap-3"><div class="w-5 h-5 rounded border-2 flex items-center justify-center ${sel ? 'bg-purple-500' : 'border-slate-600'}">${sel ? '✓' : ''}</div><div><div class="text-purple-300 text-sm">Chapter ${ch.number}</div><div class="text-sm">${ch.title}</div></div></div>`;
                c.appendChild(div);
            });
            document.getElementById('selectedCount').textContent = selectedChapters.size;
            document.getElementById('downloadBtn').disabled = selectedChapters.size === 0;
        }
        function selectAll() { selectedChapters.size === allChapters.length ? selectedChapters.clear() : (selectedChapters = new Set(allChapters.map((_,i) => i))); displayChapters(); }
        async function downloadPDF() {
            if (selectedChapters.size === 0) return;
            if (selectedChapters.size > 3) return alert('Max 3 chapter seçin!');
            const selected = Array.from(selectedChapters).map(i => allChapters[i]);
            document.getElementById('results').classList.add('hidden');
            document.getElementById('downloadProgress').classList.remove('hidden');
            document.getElementById('progressText').textContent = 'PDF oluşturuluyor (bu biraz sürebilir)...';
            document.getElementById('progressBar').style.width = '30%';
            try {
                const res = await fetch('/api/download', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({chapters: selected, title: mangaTitle})});
                if (!res.ok) throw new Error('İndirme hatası');
                const blob = await res.blob();
                const a = document.createElement('a'); a.href = URL.createObjectURL(blob); a.download = mangaTitle.replace(/[^a-z0-9]/gi,'_')+'.pdf'; a.click();
                document.getElementById('progressBar').style.width = '100%';
                document.getElementById('progressText').textContent = 'Tamamlandı! ✓';
                setTimeout(() => { document.getElementById('downloadProgress').classList.add('hidden'); document.getElementById('results').classList.remove('hidden'); }, 2000);
            } catch (err) { alert('Hata: ' + err.message); document.getElementById('downloadProgress').classList.add('hidden'); document.getElementById('results').classList.remove('hidden'); }
        }
    </script>
</body>
</html>
'''

@app.route('/')
def index():
    return render_template_string(HTML_TEMPLATE)

@app.route('/api/scrape', methods=['POST'])
def scrape_manga():
    try:
        url = request.json.get('url')
        if not url:
            return jsonify({'error': 'URL required'}), 400
        site_type = scraper.detect_site(url)
        print(f"Scraping {site_type}: {url}")
        if site_type == 'mangadex':
            result = scraper.scrape_mangadex(url)
        elif site_type == 'manganato':
            result = scraper.scrape_manganato(url)
        elif site_type == 'asura':
            result = scraper.scrape_asura(url)
        else:
            result = scraper.scrape_generic(url)
        if result and result.get('chapters'):
            return jsonify(result)
        return jsonify({'error': 'No chapters found'}), 500
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/download', methods=['POST'])
def download_chapters():
    try:
        data = request.json
        chapters = data.get('chapters', [])
        manga_title = data.get('title', 'manga')
        if not chapters:
            return jsonify({'error': 'No chapters'}), 400
        if len(chapters) > 3:
            return jsonify({'error': 'Max 3 chapters'}), 400
        
        site_type = scraper.detect_site(chapters[0].get('url', ''))
        temp_dir = tempfile.gettempdir()
        pdf_path = os.path.join(temp_dir, f"manga_{hash(manga_title)}.pdf")
        c = canvas.Canvas(pdf_path, pagesize=A4)
        width, height = A4
        
        # Cover
        c.setFont("Helvetica-Bold", 28)
        c.drawString(50, height - 100, manga_title[:40])
        c.setFont("Helvetica", 16)
        c.drawString(50, height - 140, f"{len(chapters)} Chapters")
        c.showPage()
        
        total_pages = 0
        for ch in chapters:
            print(f"Processing: {ch.get('title')}")
            c.setFont("Helvetica-Bold", 24)
            c.drawString(50, height - 100, f"Chapter {ch.get('number', '?')}")
            c.showPage()
            
            images = scraper.get_chapter_images(ch.get('url'), site_type)
            print(f"Found {len(images)} images")
            
            for i, img_url in enumerate(images):
                print(f"  [{i+1}/{len(images)}] Downloading...")
                img_data = scraper.download_image_with_proxy(img_url, ch.get('url'), site_type)
                if not img_data:
                    print(f"    Failed")
                    continue
                try:
                    img = Image.open(BytesIO(img_data))
                    if img.size[0] < 200 or img.size[1] < 200:
                        continue
                    if img.mode not in ('RGB', 'L'):
                        img = img.convert('RGB')
                    
                    aspect = img.size[1] / img.size[0]
                    pw, ph = width - 40, height - 40
                    if aspect > ph/pw:
                        nh, nw = ph, ph/aspect
                    else:
                        nw, nh = pw, pw*aspect
                    
                    buf = BytesIO()
                    img.save(buf, format='JPEG', quality=85)
                    buf.seek(0)
                    
                    c.drawImage(ImageReader(buf), (width-nw)/2, (height-nh)/2, width=nw, height=nh)
                    c.setFont("Helvetica", 8)
                    c.drawString(width/2-40, 15, f"Ch.{ch.get('number')} - Page {total_pages+1}")
                    c.showPage()
                    total_pages += 1
                    print(f"    ✓ Added")
                except Exception as e:
                    print(f"    Error: {e}")
                time.sleep(0.2)
        
        c.save()
        print(f"PDF created: {total_pages} pages")
        return send_file(pdf_path, as_attachment=True, download_name=f"{manga_title[:30]}.pdf")
    except Exception as e:
        print(f"Error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/health')
def health():
    return jsonify({'status': 'ok'})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
