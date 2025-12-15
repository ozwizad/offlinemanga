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
        """Scrape MangaDex using API"""
        try:
            manga_id = re.search(r'title/([a-f0-9-]+)', url)
            if not manga_id:
                return None
            
            manga_id = manga_id.group(1)
            
            # Get manga info
            manga_response = requests.get(f'https://api.mangadex.org/manga/{manga_id}')
            manga_data = manga_response.json()
            
            # Get title - try multiple languages
            titles = manga_data['data']['attributes']['title']
            title = titles.get('en') or titles.get('ja-ro') or titles.get('ja') or list(titles.values())[0] if titles else 'Unknown'
            
            # Get chapters with pagination
            all_chapters = []
            offset = 0
            limit = 100
            
            while True:
                api_url = f'https://api.mangadex.org/manga/{manga_id}/feed?translatedLanguage[]=en&order[chapter]=asc&limit={limit}&offset={offset}'
                response = requests.get(api_url)
                data = response.json()
                
                items = data.get('data', [])
                if not items:
                    break
                
                for item in items:
                    attrs = item['attributes']
                    chapter_num = attrs.get('chapter', 'N/A')
                    chapter_title = attrs.get('title') or f'Chapter {chapter_num}'
                    chapter_id = item['id']
                    
                    all_chapters.append({
                        'number': chapter_num,
                        'title': chapter_title,
                        'url': f'https://mangadex.org/chapter/{chapter_id}',
                        'id': chapter_id
                    })
                
                if len(items) < limit:
                    break
                offset += limit
                time.sleep(0.3)  # Rate limit
            
            print(f"MangaDex: Found {len(all_chapters)} chapters")
            return {'title': title, 'chapters': all_chapters}
        except Exception as e:
            print(f"MangaDex error: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def scrape_manganato(self, url):
        """Scrape Manganato/Chapmanganato"""
        try:
            print(f"Scraping Manganato: {url}")
            time.sleep(1)
            
            response = self.session.get(url, timeout=15)
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Get title
            title = 'Unknown Manga'
            title_elem = soup.select_one('.story-info-right h1') or soup.select_one('h1')
            if title_elem:
                title = title_elem.text.strip()
            
            print(f"Found title: {title}")
            
            # Get chapters
            chapters = []
            chapter_list = soup.select('.row-content-chapter li') or soup.select('.chapter-list .row')
            
            print(f"Found {len(chapter_list)} chapter elements")
            
            for item in chapter_list:
                link = item.select_one('a')
                if link:
                    chapter_url = link.get('href')
                    chapter_text = link.text.strip()
                    
                    # Extract chapter number
                    num_match = re.search(r'chapter[:\s-]*(\d+\.?\d*)', chapter_text, re.I)
                    chapter_num = num_match.group(1) if num_match else 'N/A'
                    
                    chapters.append({
                        'number': chapter_num,
                        'title': chapter_text,
                        'url': chapter_url
                    })
            
            # Sort by chapter number
            try:
                chapters.sort(key=lambda x: float(x['number']))
            except:
                pass
            
            print(f"Found {len(chapters)} chapters")
            return {'title': title, 'chapters': chapters}
            
        except Exception as e:
            print(f"Manganato error: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def scrape_asura(self, url):
        """Enhanced Asura Scans scraper"""
        try:
            print(f"Scraping Asura: {url}")
            
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
            
            # Get title
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
            
            # Get chapters
            chapters = []
            all_links = soup.find_all('a', href=True)
            
            for link in all_links:
                href = link.get('href', '')
                text = link.text.strip()
                
                is_chapter = False
                if '/chapter/' in href.lower() or '/ch-' in href.lower() or '/ch/' in href.lower():
                    is_chapter = True
                if 'chapter' in text.lower():
                    is_chapter = True
                
                if is_chapter:
                    num = None
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
                        if not href.startswith('http'):
                            from urllib.parse import urljoin
                            href = urljoin(url, href)
                        
                        clean_text = text if text and len(text) < 200 else f'Chapter {num}'
                        
                        chapters.append({
                            'number': num,
                            'title': clean_text,
                            'url': href
                        })
            
            # Remove duplicates
            seen = set()
            unique = []
            for ch in chapters:
                key = (ch['url'], ch['number'])
                if key not in seen:
                    seen.add(key)
                    unique.append(ch)
            
            try:
                unique.sort(key=lambda x: float(x['number']))
            except:
                pass
            
            print(f"Found {len(unique)} chapters")
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
            
            response = self.session.get(url, timeout=15)
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
            
            for link in all_links:
                href = link.get('href', '')
                text = link.text.strip()
                
                is_chapter = False
                if any(x in href.lower() for x in ['/chapter/', '/ch-', '/ch/']):
                    is_chapter = True
                elif any(x in text.lower() for x in ['chapter', 'ch.', 'ch ']):
                    is_chapter = True
                
                if is_chapter:
                    num_match = re.search(r'(\d+\.?\d*)', text)
                    if not num_match:
                        num_match = re.search(r'chapter[/-]?(\d+)', href, re.I)
                    
                    if num_match:
                        num = num_match.group(1)
                        
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
        """Get images from chapter - ONLY actual manga pages"""
        try:
            print(f"Getting images for: {chapter_url}")
            print(f"Site type: {site_type}")
            
            if site_type == 'mangadex':
                return self._get_mangadex_images(chapter_url)
            elif site_type == 'manganato':
                return self._get_manganato_images(chapter_url)
            else:
                return self._get_generic_images(chapter_url)
                
        except Exception as e:
            print(f"Get images error: {e}")
            import traceback
            traceback.print_exc()
            return []
    
    def _get_mangadex_images(self, chapter_url):
        """Get MangaDex images using API"""
        try:
            chapter_id = re.search(r'chapter/([a-f0-9-]+)', chapter_url)
            if not chapter_id:
                print("Could not extract chapter ID from URL")
                return []
            
            chapter_id = chapter_id.group(1)
            print(f"MangaDex Chapter ID: {chapter_id}")
            
            # Get image server info
            api_url = f'https://api.mangadex.org/at-home/server/{chapter_id}'
            print(f"Calling API: {api_url}")
            
            response = requests.get(api_url, timeout=15)
            print(f"API Response Status: {response.status_code}")
            
            if response.status_code != 200:
                print(f"API Error: {response.text}")
                return []
            
            data = response.json()
            
            base_url = data.get('baseUrl')
            chapter_data = data.get('chapter', {})
            chapter_hash = chapter_data.get('hash')
            
            if not base_url or not chapter_hash:
                print(f"Missing baseUrl or hash in response")
                return []
            
            # Use high quality images first, fall back to data-saver
            image_files = chapter_data.get('data', [])
            quality = 'data'
            
            if not image_files:
                image_files = chapter_data.get('dataSaver', [])
                quality = 'data-saver'
            
            print(f"Found {len(image_files)} image files (quality: {quality})")
            
            images = []
            for filename in image_files:
                img_url = f'{base_url}/{quality}/{chapter_hash}/{filename}'
                images.append(img_url)
            
            print(f"Generated {len(images)} image URLs")
            return images
            
        except Exception as e:
            print(f"MangaDex API Error: {e}")
            import traceback
            traceback.print_exc()
            return []
    
    def _get_manganato_images(self, chapter_url):
        """Get Manganato images with proper referer"""
        try:
            print(f"Fetching Manganato chapter: {chapter_url}")
            
            # Use session with proper headers
            headers = self.headers.copy()
            headers['Referer'] = chapter_url
            
            response = self.session.get(chapter_url, headers=headers, timeout=15)
            print(f"Page response: {response.status_code}")
            
            soup = BeautifulSoup(response.content, 'html.parser')
            
            images = []
            
            # Manganato uses specific container
            container = soup.select_one('.container-chapter-reader') or soup.select_one('.reading-content') or soup
            
            for img in container.find_all('img'):
                src = img.get('src') or img.get('data-src') or img.get('data-lazy-src')
                
                if not src:
                    continue
                
                # Filter out non-manga images
                skip_patterns = ['logo', 'icon', 'avatar', 'banner', 'ad', 'advertisement',
                               'facebook', 'twitter', 'discord', '.gif', 'emoji']
                
                if any(pattern in src.lower() for pattern in skip_patterns):
                    continue
                
                # Must be image file
                if not any(ext in src.lower() for ext in ['.jpg', '.jpeg', '.png', '.webp']):
                    continue
                
                if not src.startswith('http'):
                    from urllib.parse import urljoin
                    src = urljoin(chapter_url, src)
                
                images.append(src)
            
            # Remove duplicates
            images = list(dict.fromkeys(images))
            
            print(f"Found {len(images)} manga images")
            return images
            
        except Exception as e:
            print(f"Manganato images error: {e}")
            import traceback
            traceback.print_exc()
            return []
    
    def _get_generic_images(self, chapter_url):
        """Get images from generic sites"""
        try:
            print(f"Fetching page: {chapter_url}")
            response = self.session.get(chapter_url, timeout=15)
            print(f"Page response: {response.status_code}")
            
            soup = BeautifulSoup(response.content, 'html.parser')
            
            images = []
            
            # Look for reader containers
            reader_containers = soup.find_all(['div', 'section'], class_=lambda x: x and any(
                word in str(x).lower() for word in ['reader', 'chapter', 'page', 'image-container', 'content']
            ))
            
            search_area = reader_containers if reader_containers else [soup]
            
            for container in search_area:
                for img in container.find_all('img'):
                    src = img.get('src') or img.get('data-src') or img.get('data-lazy-src') or img.get('data-original')
                    
                    if not src:
                        continue
                    
                    skip_patterns = ['logo', 'icon', 'avatar', 'banner', 'ad', 'advertisement',
                                   'facebook', 'twitter', 'discord', 'patreon', 'button', 'nav',
                                   'header', 'footer', 'sidebar', '.gif', 'emoji', 'badge', 'flag']
                    
                    if any(pattern in src.lower() for pattern in skip_patterns):
                        continue
                    
                    if not any(ext in src.lower() for ext in ['.jpg', '.jpeg', '.png', '.webp']):
                        continue
                    
                    width = img.get('width') or img.get('data-width')
                    height = img.get('height') or img.get('data-height')
                    
                    if width and height:
                        try:
                            if int(width) < 200 or int(height) < 200:
                                continue
                        except:
                            pass
                    
                    if not src.startswith('http'):
                        from urllib.parse import urljoin
                        src = urljoin(chapter_url, src)
                    
                    images.append(src)
            
            # Remove duplicates
            images = list(dict.fromkeys(images))
            
            print(f"Found {len(images)} manga images")
            return images
            
        except Exception as e:
            print(f"Generic images error: {e}")
            import traceback
            traceback.print_exc()
            return []
    
    def download_image(self, img_url, referer_url, site_type='generic'):
        """Download image with proper headers for each site"""
        try:
            headers = self.headers.copy()
            
            # Site-specific headers
            if site_type == 'mangadex':
                headers['Referer'] = 'https://mangadex.org/'
                headers['Accept'] = 'image/webp,image/apng,image/*,*/*;q=0.8'
            elif site_type == 'manganato':
                # Manganato needs specific referer
                headers['Referer'] = referer_url
                headers['Accept'] = 'image/webp,image/apng,image/*,*/*;q=0.8'
                # Try to extract the actual domain
                from urllib.parse import urlparse
                parsed = urlparse(img_url)
                headers['Origin'] = f'{parsed.scheme}://{parsed.netloc}'
            else:
                headers['Referer'] = referer_url
            
            response = requests.get(img_url, headers=headers, timeout=30, stream=True)
            
            if response.status_code == 403:
                print(f"  403 Forbidden - trying alternative headers...")
                # Try with different user agent
                headers['User-Agent'] = 'Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Mobile/15E148 Safari/604.1'
                response = requests.get(img_url, headers=headers, timeout=30, stream=True)
            
            return response
            
        except Exception as e:
            print(f"Download image error: {e}")
            return None


scraper = MangaScraper()

# HTML Template
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
                <div>✓ <strong>En İyi:</strong> MangaDex (API var, %100 çalışır)</div>
                <div>✓ <strong>İyi:</strong> Manganato (stabil)</div>
                <div>⚠️ <strong>Sınırlı:</strong> Asura Scans (Cloudflare korumalı)</div>
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
        
        print(f"\n{'='*60}")
        print(f"SCRAPING REQUEST")
        print(f"URL: {url}")
        print(f"{'='*60}")
        
        site_type = scraper.detect_site(url)
        print(f"Detected site type: {site_type}")
        
        result = None
        if site_type == 'mangadex':
            print("Using MangaDex API scraper...")
            result = scraper.scrape_mangadex(url)
        elif site_type == 'manganato':
            print("Using Manganato scraper...")
            result = scraper.scrape_manganato(url)
        elif site_type == 'asura':
            print("Using Asura scraper (limited due to Cloudflare)...")
            result = scraper.scrape_asura(url)
        else:
            print("Using generic scraper...")
            result = scraper.scrape_generic(url)
        
        if result and result.get('chapters'):
            print(f"✓ SUCCESS: Found {len(result['chapters'])} chapters")
            print(f"✓ Title: {result['title']}")
            return jsonify(result)
        else:
            print("✗ FAILED: No chapters found")
            return jsonify({'error': 'No chapters found. Try MangaDex or Manganato for best results.'}), 500
            
    except Exception as e:
        print(f"✗ ERROR: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@app.route('/api/download', methods=['POST'])
def download_chapters():
    """Create and download PDF with actual manga images"""
    try:
        data = request.json
        chapters = data.get('chapters', [])
        manga_title = data.get('title', 'manga')
        
        if not chapters:
            return jsonify({'error': 'No chapters'}), 400
        
        # Limit for safety
        if len(chapters) > 5:
            return jsonify({'error': 'Maximum 5 chapters at once'}), 400
        
        print(f"\n{'='*60}")
        print(f"CREATING PDF")
        print(f"Manga: {manga_title}")
        print(f"Chapters: {len(chapters)}")
        print(f"{'='*60}")
        
        # Detect site type from first chapter URL
        first_url = chapters[0].get('url', '')
        site_type = scraper.detect_site(first_url)
        print(f"Site type: {site_type}")
        
        # Create PDF
        temp_dir = tempfile.gettempdir()
        pdf_path = os.path.join(temp_dir, f"manga_{hash(manga_title)}.pdf")
        
        c = canvas.Canvas(pdf_path, pagesize=A4)
        width, height = A4
        
        # Cover page
        c.setFont("Helvetica-Bold", 28)
        title_text = manga_title[:50]
        c.drawString(50, height - 100, title_text)
        c.setFont("Helvetica", 16)
        c.drawString(50, height - 140, f"{len(chapters)} Chapters")
        c.setFont("Helvetica-Oblique", 10)
        c.drawString(50, height - 170, "High Quality Manga PDF")
        c.showPage()
        
        total_pages = 0
        
        # Process each chapter
        for chapter_idx, ch in enumerate(chapters):
            chapter_url = ch.get('url')
            chapter_title = ch.get('title', f"Chapter {ch.get('number', '?')}")
            
            print(f"\n{'='*50}")
            print(f"Processing Chapter {chapter_idx + 1}/{len(chapters)}: {chapter_title}")
            print(f"URL: {chapter_url}")
            print(f"{'='*50}")
            
            # Chapter title page
            c.setFont("Helvetica-Bold", 24)
            c.drawString(50, height - 100, f"Chapter {ch.get('number', '?')}")
            c.setFont("Helvetica", 14)
            if len(chapter_title) > 50:
                c.drawString(50, height - 130, chapter_title[:50])
                c.drawString(50, height - 150, chapter_title[50:100])
            else:
                c.drawString(50, height - 130, chapter_title)
            c.showPage()
            
            # Get images for this chapter
            try:
                images = scraper.get_chapter_images(chapter_url, site_type)
                print(f"Found {len(images)} images")
                
                if not images:
                    c.setFont("Helvetica", 12)
                    c.drawString(50, height/2, "No images found for this chapter")
                    c.drawString(50, height/2 - 30, f"Visit: {chapter_url[:70]}")
                    c.showPage()
                    continue
                
                print(f"Downloading {len(images)} images...")
                
                successful_images = 0
                failed_images = 0
                
                for img_idx, img_url in enumerate(images):
                    try:
                        print(f"  [{img_idx + 1}/{len(images)}] {img_url[:60]}...")
                        
                        # Download with retry
                        img_response = None
                        for retry in range(3):
                            img_response = scraper.download_image(img_url, chapter_url, site_type)
                            
                            if img_response and img_response.status_code == 200:
                                break
                            
                            print(f"    Retry {retry + 1}/3: Status {img_response.status_code if img_response else 'None'}")
                            time.sleep(1)
                        
                        if not img_response or img_response.status_code != 200:
                            print(f"    ✗ Failed after retries")
                            failed_images += 1
                            continue
                        
                        # Verify it's an image
                        content_type = img_response.headers.get('content-type', '')
                        if 'image' not in content_type.lower() and len(img_response.content) < 1000:
                            print(f"    ✗ Not a valid image")
                            failed_images += 1
                            continue
                        
                        # Open image
                        img = Image.open(BytesIO(img_response.content))
                        
                        # Skip small images
                        if img.size[0] < 300 or img.size[1] < 300:
                            print(f"    ✗ Too small ({img.size})")
                            failed_images += 1
                            continue
                        
                        # Convert to RGB
                        if img.mode not in ('RGB', 'L'):
                            img = img.convert('RGB')
                        
                        # Calculate dimensions
                        img_width, img_height = img.size
                        aspect_ratio = img_height / img_width
                        
                        page_width = width - 40
                        page_height = height - 40
                        
                        if aspect_ratio > (page_height / page_width):
                            new_height = page_height
                            new_width = new_height / aspect_ratio
                        else:
                            new_width = page_width
                            new_height = new_width * aspect_ratio
                        
                        x_pos = (width - new_width) / 2
                        y_pos = (height - new_height) / 2
                        
                        # Save to buffer
                        temp_img = BytesIO()
                        if img.mode == 'L':
                            img.save(temp_img, format='JPEG', quality=95, optimize=True)
                        else:
                            img.save(temp_img, format='JPEG', quality=90, optimize=True)
                        temp_img.seek(0)
                        
                        # Add to PDF
                        c.drawImage(
                            ImageReader(temp_img),
                            x_pos, y_pos,
                            width=new_width,
                            height=new_height,
                            preserveAspectRatio=True
                        )
                        
                        # Page number
                        c.setFont("Helvetica", 8)
                        c.drawString(width/2 - 50, 15, f"Ch.{ch.get('number')} - Page {successful_images + 1}")
                        
                        c.showPage()
                        successful_images += 1
                        total_pages += 1
                        print(f"    ✓ Added to PDF")
                        
                        time.sleep(0.3)
                        
                    except Exception as img_error:
                        print(f"    ✗ Error: {img_error}")
                        failed_images += 1
                        continue
                
                print(f"Chapter complete: {successful_images} pages, {failed_images} failed")
                
                if successful_images == 0:
                    c.setFont("Helvetica", 12)
                    c.drawString(50, height/2, f"Could not load images for this chapter")
                    c.drawString(50, height/2 - 30, f"Site may have hotlink protection")
                    c.drawString(50, height/2 - 50, f"Try: MangaDex for best results")
                    c.showPage()
                
            except Exception as chapter_error:
                print(f"Chapter error: {chapter_error}")
                import traceback
                traceback.print_exc()
                
                c.setFont("Helvetica", 12)
                c.drawString(50, height/2, f"Failed to process chapter")
                c.drawString(50, height/2 - 30, f"Error: {str(chapter_error)[:60]}")
                c.showPage()
                continue
        
        # Save PDF
        c.save()
        
        print(f"\n{'='*60}")
        print(f"✓ PDF CREATED: {pdf_path}")
        print(f"✓ Total pages: {total_pages}")
        print(f"{'='*60}\n")
        
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

@app.route('/api/test-mangadex')
def test_mangadex():
    """Test MangaDex API"""
    try:
        # Test with One Punch Man
        chapter_id = "32d1a84e-0b7c-4d38-a634-38b7e4cd3a43"  # Sample chapter
        api_url = f'https://api.mangadex.org/at-home/server/{chapter_id}'
        
        response = requests.get(api_url, timeout=10)
        data = response.json()
        
        result = {
            'status': response.status_code,
            'baseUrl': data.get('baseUrl'),
            'hash': data.get('chapter', {}).get('hash'),
            'image_count': len(data.get('chapter', {}).get('data', [])),
            'sample_image': None
        }
        
        if result['baseUrl'] and result['hash']:
            images = data.get('chapter', {}).get('data', [])
            if images:
                result['sample_image'] = f"{result['baseUrl']}/data/{result['hash']}/{images[0]}"
        
        return jsonify(result)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
