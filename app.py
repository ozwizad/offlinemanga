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

app = Flask(__name__)
CORS(app)

class MangaScraper:
    def __init__(self):
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
        }
    
    def detect_site(self, url):
        if 'mangadex.org' in url:
            return 'mangadex'
        elif 'asuracomic' in url or 'asura' in url:
            return 'asura'
        elif 'manganato' in url or 'chapmanganato' in url:
            return 'manganato'
        return 'generic'
    
    def scrape_mangadex(self, url):
        """Scrape MangaDex using API"""
        try:
            manga_id = re.search(r'title/([a-f0-9-]+)', url)
            if not manga_id:
                return None
            
            manga_id = manga_id.group(1)
            
            # Get manga info
            manga_response = requests.get(f'https://api.mangadex.org/manga/{manga_id}')
            manga_data = manga_response.json()
            title = manga_data['data']['attributes']['title'].get('en', 'Unknown')
            
            # Get chapters
            api_url = f'https://api.mangadex.org/manga/{manga_id}/feed?translatedLanguage[]=en&order[chapter]=asc&limit=500'
            response = requests.get(api_url)
            data = response.json()
            
            chapters = []
            for item in data.get('data', []):
                attrs = item['attributes']
                chapter_num = attrs.get('chapter', 'N/A')
                chapter_title = attrs.get('title', f'Chapter {chapter_num}')
                chapter_id = item['id']
                
                chapters.append({
                    'number': chapter_num,
                    'title': chapter_title,
                    'url': f'https://mangadex.org/chapter/{chapter_id}',
                    'id': chapter_id
                })
            
            return {'title': title, 'chapters': chapters}
        except Exception as e:
            print(f"MangaDex error: {e}")
            return None
    
    def scrape_asura(self, url):
        """Enhanced Asura Scans scraper"""
        try:
            print(f"Scraping Asura: {url}")
            
            # Try multiple approaches
            session = requests.Session()
            session.headers.update({
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.5',
                'Referer': 'https://asuracomic.net/',
            })
            
            time.sleep(2)
            response = session.get(url, timeout=20)
            
            if response.status_code != 200:
                print(f"Bad status: {response.status_code}")
                return None
            
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Get title - try multiple selectors
            title = 'Unknown Manga'
            for selector in ['h1', 'h2', 'h3', '[class*="title"]', '[class*="Title"]']:
                elems = soup.select(selector)
                for elem in elems:
                    text = elem.text.strip()
                    if len(text) > 3 and len(text) < 100 and 'chapter' not in text.lower():
                        title = text
                        break
                if title != 'Unknown Manga':
                    break
            
            print(f"Found title: {title}")
            
            # Get chapters - look for ALL links
            chapters = []
            all_links = soup.find_all('a', href=True)
            
            print(f"Total links found: {len(all_links)}")
            
            for link in all_links:
                href = link.get('href', '')
                text = link.text.strip()
                
                # Asura chapter patterns
                is_chapter = False
                
                # Check URL patterns
                if '/chapter/' in href.lower():
                    is_chapter = True
                elif '/ch-' in href.lower() or '/ch/' in href.lower():
                    is_chapter = True
                
                # Check text patterns
                if 'chapter' in text.lower():
                    is_chapter = True
                
                if is_chapter:
                    # Extract chapter number - try multiple patterns
                    num = None
                    
                    # From text
                    matches = [
                        re.search(r'chapter[:\s-]*(\d+\.?\d*)', text, re.I),
                        re.search(r'ch[:\s-]*(\d+\.?\d*)', text, re.I),
                        re.search(r'#(\d+\.?\d*)', text),
                        re.search(r'^(\d+\.?\d*)', text),
                    ]
                    
                    for match in matches:
                        if match:
                            num = match.group(1)
                            break
                    
                    # From URL if not found
                    if not num:
                        url_matches = [
                            re.search(r'/chapter[/-](\d+\.?\d*)', href, re.I),
                            re.search(r'/ch[/-](\d+\.?\d*)', href, re.I),
                        ]
                        for match in url_matches:
                            if match:
                                num = match.group(1)
                                break
                    
                    if num:
                        # Make URL absolute
                        if not href.startswith('http'):
                            from urllib.parse import urljoin
                            href = urljoin(url, href)
                        
                        # Clean title
                        clean_text = text if text and len(text) < 200 else f'Chapter {num}'
                        
                        chapters.append({
                            'number': num,
                            'title': clean_text,
                            'url': href
                        })
            
            print(f"Found {len(chapters)} potential chapters before dedup")
            
            # Remove duplicates
            seen = set()
            unique = []
            for ch in chapters:
                # Use both URL and number for dedup
                key = (ch['url'], ch['number'])
                if key not in seen:
                    seen.add(key)
                    unique.append(ch)
            
            # Sort by chapter number
            try:
                unique.sort(key=lambda x: float(x['number']))
            except:
                print("Could not sort chapters")
                pass
            
            print(f"Final unique chapters: {len(unique)}")
            
            if len(unique) == 0:
                print("No chapters found! Debugging info:")
                # Print some sample links for debugging
                sample_links = [(l.get('href', '')[:50], l.text.strip()[:30]) for l in all_links[:10]]
                print(f"Sample links: {sample_links}")
            
            return {'title': title, 'chapters': unique}
            
        except Exception as e:
            print(f"Asura scrape error: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def scrape_generic(self, url):
        """Generic scraper for most sites"""
        try:
            print(f"Scraping: {url}")
            time.sleep(1)
            
            response = requests.get(url, headers=self.headers, timeout=15)
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Get title
            title = 'Unknown Manga'
            for selector in ['h1', 'h2', '.manga-title', '.title']:
                elem = soup.select_one(selector)
                if elem and len(elem.text.strip()) > 3:
                    title = elem.text.strip()
                    break
            
            # Get chapters
            chapters = []
            all_links = soup.find_all('a', href=True)
            
            print(f"Found {len(all_links)} total links")
            
            for link in all_links:
                href = link.get('href', '')
                text = link.text.strip()
                
                # Look for chapter patterns
                is_chapter = False
                if any(x in href.lower() for x in ['/chapter/', '/ch-', '/ch/']):
                    is_chapter = True
                elif any(x in text.lower() for x in ['chapter', 'ch.', 'ch ']):
                    is_chapter = True
                
                if is_chapter:
                    # Extract number
                    num_match = re.search(r'(\d+\.?\d*)', text)
                    if not num_match:
                        num_match = re.search(r'chapter[/-]?(\d+)', href, re.I)
                    
                    if num_match:
                        num = num_match.group(1)
                        
                        # Make absolute URL
                        if not href.startswith('http'):
                            from urllib.parse import urljoin
                            href = urljoin(url, href)
                        
                        chapters.append({
                            'number': num,
                            'title': text[:100] if text else f'Chapter {num}',
                            'url': href
                        })
            
            # Remove duplicates
            seen = set()
            unique = []
            for ch in chapters:
                if ch['url'] not in seen:
                    seen.add(ch['url'])
                    unique.append(ch)
            
            # Sort
            try:
                unique.sort(key=lambda x: float(x['number']))
            except:
                pass
            
            print(f"Found {len(unique)} chapters")
            return {'title': title, 'chapters': unique}
            
        except Exception as e:
            print(f"Generic scrape error: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def get_chapter_images(self, chapter_url, site_type='generic'):
        """Get images from chapter"""
        try:
            if site_type == 'mangadex':
                chapter_id = re.search(r'chapter/([a-f0-9-]+)', chapter_url)
                if chapter_id:
                    api_url = f'https://api.mangadex.org/at-home/server/{chapter_id.group(1)}'
                    data = requests.get(api_url).json()
                    base_url = data['baseUrl']
                    chapter_hash = data['chapter']['hash']
                    
                    images = []
                    for filename in data['chapter']['data']:
                        images.append(f'{base_url}/data/{chapter_hash}/{filename}')
                    return images
            
            # Generic image extraction
            response = requests.get(chapter_url, headers=self.headers, timeout=10)
            soup = BeautifulSoup(response.content, 'html.parser')
            
            images = []
            for img in soup.find_all('img'):
                src = img.get('src') or img.get('data-src') or img.get('data-lazy-src')
                if src and any(ext in src.lower() for ext in ['.jpg', '.jpeg', '.png', '.webp']):
                    if not src.startswith('http'):
                        from urllib.parse import urljoin
                        src = urljoin(chapter_url, src)
                    images.append(src)
            
            return images
        except Exception as e:
            print(f"Get images error: {e}")
            return []

scraper = MangaScraper()

# HTML Template for the web interface
HTML_TEMPLATE = '''
<!DOCTYPE html>
<html lang="tr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Manga Downloader</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <link href="https://fonts.googleapis.com/css2?family=Orbitron:wght@400;700;900&family=Rajdhani:wght@600;700&display=swap" rel="stylesheet">
    <style>
        @keyframes shimmer {
            0% { background-position: 0% 50%; }
            100% { background-position: 200% 50%; }
        }
        .shimmer-text {
            background: linear-gradient(to right, #a855f7, #ec4899, #a855f7);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            background-size: 200% auto;
            animation: shimmer 3s linear infinite;
        }
        .custom-scrollbar::-webkit-scrollbar { width: 8px; }
        .custom-scrollbar::-webkit-scrollbar-track { background: rgba(30, 27, 75, 0.5); border-radius: 10px; }
        .custom-scrollbar::-webkit-scrollbar-thumb { background: linear-gradient(to bottom, #a855f7, #ec4899); border-radius: 10px; }
    </style>
</head>
<body class="min-h-screen bg-gradient-to-br from-slate-950 via-purple-950 to-slate-900 text-white">
    <div class="container mx-auto px-4 py-8 max-w-4xl">
        <div class="text-center mb-12">
            <h1 class="text-5xl font-black mb-3 shimmer-text" style="font-family: 'Orbitron', monospace">
                MANGA DOWNLOADER
            </h1>
            <p class="text-purple-300 font-mono">&gt; Link yapıştır → Chapter seç → İndir_</p>
        </div>

        <div class="bg-slate-900/50 backdrop-blur-sm border border-purple-500/30 rounded-2xl p-6 mb-6">
            <label class="block text-purple-300 font-mono text-sm mb-3">&lt;MANGA_URL /&gt;</label>
            <div class="flex gap-3">
                <input type="text" id="mangaUrl" placeholder="https://mangasite.com/manga/..." 
                    class="flex-1 bg-slate-950/70 border-2 border-purple-500/50 rounded-xl px-4 py-3 text-white placeholder-purple-400/50 focus:outline-none focus:border-purple-400 font-mono">
                <button onclick="scrape()" id="scrapeBtn"
                    class="px-6 py-3 bg-gradient-to-r from-purple-600 to-pink-600 hover:from-purple-500 hover:to-pink-500 rounded-xl font-bold">
                    TARA
                </button>
            </div>
            <div class="text-xs text-purple-400/70 mt-2 font-mono">
                ✓ MangaDex, Manganato, Asura Scans desteklenir
            </div>
        </div>

        <div id="loading" class="hidden text-center py-16">
            <div class="animate-spin rounded-full h-12 w-12 border-b-2 border-purple-400 mx-auto mb-4"></div>
            <p class="text-purple-300">Analiz ediliyor...</p>
        </div>

        <div id="results" class="hidden bg-slate-900/50 backdrop-blur-sm border border-purple-500/30 rounded-2xl p-6">
            <div class="flex justify-between items-center mb-4">
                <h2 id="mangaTitle" class="text-2xl font-bold" style="font-family: 'Orbitron'"></h2>
                <button onclick="selectAll()" class="px-4 py-2 bg-purple-600/30 border border-purple-400/50 rounded-lg text-sm">
                    Tümünü Seç
                </button>
            </div>

            <div class="mb-4 flex gap-2 items-center">
                <span class="text-purple-300 font-mono">Seçilen: <span id="selectedCount">0</span></span>
                <button onclick="downloadPDF()" id="downloadBtn" disabled
                    class="px-6 py-2 bg-gradient-to-r from-pink-600 to-purple-600 hover:from-pink-500 hover:to-purple-500 disabled:opacity-50 rounded-lg font-bold">
                    📥 PDF İNDİR
                </button>
            </div>

            <div id="chapters" class="space-y-2 max-h-96 overflow-y-auto custom-scrollbar"></div>
        </div>

        <div id="downloadProgress" class="hidden bg-slate-900/50 backdrop-blur-sm border border-purple-500/30 rounded-2xl p-6 mt-6">
            <div class="text-center mb-4">
                <div class="text-xl font-bold mb-2">İNDİRİLİYOR...</div>
                <div id="progressText" class="text-purple-300 text-sm"></div>
            </div>
            <div class="w-full bg-slate-800 rounded-full h-3">
                <div id="progressBar" class="h-full bg-gradient-to-r from-purple-600 to-pink-600 rounded-full transition-all" style="width: 0%"></div>
            </div>
        </div>
    </div>

    <script>
        let allChapters = [];
        let selectedChapters = new Set();
        let mangaTitle = '';

        async function scrape() {
            const url = document.getElementById('mangaUrl').value.trim();
            if (!url) return alert('Lütfen bir link girin!');

            document.getElementById('loading').classList.remove('hidden');
            document.getElementById('results').classList.add('hidden');

            try {
                const res = await fetch('/api/scrape', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({url})
                });

                const data = await res.json();
                
                if (!res.ok || !data.chapters || data.chapters.length === 0) {
                    throw new Error(data.error || 'Chapter bulunamadı');
                }

                allChapters = data.chapters;
                mangaTitle = data.title;
                selectedChapters.clear();

                document.getElementById('mangaTitle').textContent = mangaTitle;
                displayChapters();

                document.getElementById('loading').classList.add('hidden');
                document.getElementById('results').classList.remove('hidden');

            } catch (err) {
                document.getElementById('loading').classList.add('hidden');
                alert('Hata: ' + err.message);
            }
        }

        function displayChapters() {
            const container = document.getElementById('chapters');
            container.innerHTML = '';

            allChapters.forEach((ch, idx) => {
                const selected = selectedChapters.has(idx);
                const div = document.createElement('div');
                div.className = `p-3 rounded-lg cursor-pointer border-2 transition ${
                    selected ? 'bg-purple-600/30 border-purple-400' : 'bg-slate-800/50 border-slate-700/50 hover:border-purple-500/50'
                }`;
                div.onclick = () => toggleChapter(idx);
                div.innerHTML = `
                    <div class="flex items-center gap-3">
                        <div class="w-5 h-5 rounded border-2 flex items-center justify-center ${
                            selected ? 'bg-purple-500 border-purple-400' : 'border-slate-600'
                        }">
                            ${selected ? '✓' : ''}
                        </div>
                        <div>
                            <div class="font-mono text-purple-300 text-sm">Chapter ${ch.number}</div>
                            <div class="font-semibold text-sm">${ch.title}</div>
                        </div>
                    </div>
                `;
                container.appendChild(div);
            });

            updateCounts();
        }

        function toggleChapter(idx) {
            if (selectedChapters.has(idx)) {
                selectedChapters.delete(idx);
            } else {
                selectedChapters.add(idx);
            }
            displayChapters();
        }

        function selectAll() {
            if (selectedChapters.size === allChapters.length) {
                selectedChapters.clear();
            } else {
                selectedChapters = new Set(allChapters.map((_, i) => i));
            }
            displayChapters();
        }

        function updateCounts() {
            document.getElementById('selectedCount').textContent = selectedChapters.size;
            document.getElementById('downloadBtn').disabled = selectedChapters.size === 0;
        }

        async function downloadPDF() {
            if (selectedChapters.size === 0) return;
            if (selectedChapters.size > 10) {
                if (!confirm(`${selectedChapters.size} chapter seçtiniz. Bu uzun sürebilir. Devam?`)) return;
            }

            const selected = Array.from(selectedChapters).map(i => allChapters[i]);

            document.getElementById('results').classList.add('hidden');
            document.getElementById('downloadProgress').classList.remove('hidden');
            document.getElementById('progressText').textContent = 'PDF oluşturuluyor...';
            document.getElementById('progressBar').style.width = '30%';

            try {
                const res = await fetch('/api/download', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({chapters: selected, title: mangaTitle})
                });

                document.getElementById('progressBar').style.width = '60%';

                if (!res.ok) throw new Error('İndirme hatası');

                const blob = await res.blob();
                const url = URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = url;
                a.download = `${mangaTitle.replace(/[^a-z0-9]/gi, '_')}.pdf`;
                a.click();
                URL.revokeObjectURL(url);

                document.getElementById('progressBar').style.width = '100%';
                document.getElementById('progressText').textContent = 'Tamamlandı! ✓';

                setTimeout(() => {
                    document.getElementById('downloadProgress').classList.add('hidden');
                    document.getElementById('results').classList.remove('hidden');
                    document.getElementById('progressBar').style.width = '0%';
                }, 2000);

            } catch (err) {
                alert('İndirme hatası: ' + err.message);
                document.getElementById('downloadProgress').classList.add('hidden');
                document.getElementById('results').classList.remove('hidden');
            }
        }
    </script>
</body>
</html>
'''

@app.route('/')
def index():
    """Serve the web interface"""
    return render_template_string(HTML_TEMPLATE)

@app.route('/api/scrape', methods=['POST'])
def scrape_manga():
    """Scrape manga chapters from URL"""
    try:
        data = request.json
        url = data.get('url')
        
        if not url:
            return jsonify({'error': 'URL required'}), 400
        
        print(f"Scraping: {url}")
        
        site_type = scraper.detect_site(url)
        print(f"Site type: {site_type}")
        
        result = None
        if site_type == 'mangadex':
            result = scraper.scrape_mangadex(url)
        elif site_type == 'asura':
            result = scraper.scrape_asura(url)
        else:
            result = scraper.scrape_generic(url)
        
        if result and result.get('chapters'):
            print(f"Success: {len(result['chapters'])} chapters")
            return jsonify(result)
        else:
            return jsonify({'error': 'No chapters found'}), 500
            
    except Exception as e:
        print(f"Scrape error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@app.route('/api/download', methods=['POST'])
def download_chapters():
    """Create and download PDF"""
    try:
        data = request.json
        chapters = data.get('chapters', [])
        manga_title = data.get('title', 'manga')
        
        if not chapters:
            return jsonify({'error': 'No chapters'}), 400
        
        print(f"Creating PDF for {len(chapters)} chapters")
        
        # Create PDF
        temp_dir = tempfile.gettempdir()
        pdf_path = os.path.join(temp_dir, f"manga_{hash(manga_title)}.pdf")
        
        c = canvas.Canvas(pdf_path, pagesize=A4)
        width, height = A4
        
        # Cover
        c.setFont("Helvetica-Bold", 24)
        c.drawString(50, height - 100, manga_title[:50])
        c.setFont("Helvetica", 14)
        c.drawString(50, height - 130, f"{len(chapters)} Chapters")
        c.showPage()
        
        # Chapter pages
        for idx, ch in enumerate(chapters):
            c.setFont("Helvetica-Bold", 16)
            c.drawString(50, height - 80, f"Chapter {ch['number']}")
            c.setFont("Helvetica", 11)
            c.drawString(50, height - 105, ch['title'][:70])
            c.setFont("Helvetica", 8)
            c.drawString(50, height - 125, f"URL: {ch['url'][:80]}")
            c.setFont("Helvetica-Oblique", 9)
            c.drawString(50, height - 145, f"({idx + 1} / {len(chapters)})")
            c.showPage()
        
        c.save()
        print(f"PDF created: {pdf_path}")
        
        return send_file(pdf_path, as_attachment=True, download_name=f"{manga_title[:30]}.pdf")
        
    except Exception as e:
        print(f"Download error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@app.route('/health')
def health():
    """Health check"""
    return jsonify({'status': 'ok'})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
