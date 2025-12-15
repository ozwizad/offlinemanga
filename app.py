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
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'image/webp,*/*',
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
            resp = self.session.get(url, timeout=10)
            soup = BeautifulSoup(resp.content, 'html.parser')
            title_elem = soup.select_one('.story-info-right h1') or soup.select_one('h1')
            title = title_elem.text.strip() if title_elem else 'Unknown'
            chapters = []
            for item in soup.select('.row-content-chapter li'):
                link = item.select_one('a')
                if link:
                    text = link.text.strip()
                    num = re.search(r'chapter[:\s-]*(\d+\.?\d*)', text, re.I)
                    chapters.append({
                        'number': num.group(1) if num else 'N/A',
                        'title': text,
                        'url': link.get('href')
                    })
            chapters.sort(key=lambda x: float(x['number']) if x['number'] != 'N/A' else 0)
            return {'title': title, 'chapters': chapters}
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
                href, text = link.get('href', ''), link.text.strip()
                if '/chapter/' in href.lower() or 'chapter' in text.lower():
                    num = re.search(r'chapter[:\s-]*(\d+)', text, re.I) or re.search(r'/chapter[/-](\d+)', href, re.I)
                    if num:
                        if not href.startswith('http'):
                            href = urljoin(url, href)
                        chapters.append({'number': num.group(1), 'title': text[:80], 'url': href})
            seen = set()
            unique = [c for c in chapters if c['url'] not in seen and not seen.add(c['url'])]
            unique.sort(key=lambda x: float(x['number']))
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
                hash_ = ch.get('hash')
                files = ch.get('dataSaver', []) or ch.get('data', [])
                quality = 'data-saver' if ch.get('dataSaver') else 'data'
                return [f'{base}/{quality}/{hash_}/{f}' for f in files] if base and hash_ else []
            
            resp = self.session.get(url, timeout=10)
            soup = BeautifulSoup(resp.content, 'html.parser')
            container = soup.select_one('.container-chapter-reader') or soup
            images = []
            for img in container.find_all('img'):
                src = img.get('src') or img.get('data-src')
                if src and any(ext in src.lower() for ext in ['.jpg', '.png', '.webp']):
                    if not any(skip in src.lower() for skip in ['logo', 'icon', 'ad', '.gif']):
                        if not src.startswith('http'):
                            src = urljoin(url, src)
                        images.append(src)
            return list(dict.fromkeys(images))
        except Exception as e:
            print(f"Get images error: {e}")
            return []
    
    def download_image(self, img_url, referer):
        """Download single image with proxy fallback"""
        # Try wsrv.nl proxy first (best for bypassing hotlink)
        try:
            proxy = f"https://wsrv.nl/?url={quote(img_url, safe='')}&n=-1"
            r = requests.get(proxy, timeout=12)
            if r.status_code == 200 and len(r.content) > 500:
                return (img_url, r.content)
        except:
            pass
        # Direct fallback
        try:
            r = requests.get(img_url, headers={'Referer': referer, 'User-Agent': self.headers['User-Agent']}, timeout=10)
            if r.status_code == 200 and len(r.content) > 500:
                return (img_url, r.content)
        except:
            pass
        return (img_url, None)
    
    def download_parallel(self, urls, referer, workers=6):
        """Download images in parallel"""
        results = {}
        with ThreadPoolExecutor(max_workers=workers) as ex:
            futures = {ex.submit(self.download_image, u, referer): u for u in urls}
            for f in as_completed(futures):
                url, data = f.result()
                if data:
                    results[url] = data
        return results


scraper = MangaScraper()

HTML = '''<!DOCTYPE html>
<html><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Manga PDF</title>
<script src="https://cdn.tailwindcss.com"></script>
<style>@keyframes s{0%{background-position:0 50%}100%{background-position:200% 50%}}.sh{background:linear-gradient(90deg,#a855f7,#ec4899,#a855f7);-webkit-background-clip:text;-webkit-text-fill-color:transparent;background-size:200% auto;animation:s 3s linear infinite}</style>
</head><body class="min-h-screen bg-gradient-to-br from-slate-950 via-purple-950 to-slate-900 text-white p-4">
<div class="max-w-3xl mx-auto">
<h1 class="text-4xl font-black text-center mb-2 sh">MANGA DOWNLOADER</h1>
<p class="text-center text-purple-300 mb-8">Link yapıştır → Chapter seç → PDF indir</p>
<div class="bg-slate-900/50 border border-purple-500/30 rounded-xl p-4 mb-4">
<div class="flex gap-2">
<input id="url" placeholder="https://manganato.gg/manga/..." class="flex-1 bg-slate-950 border border-purple-500/50 rounded-lg px-3 py-2">
<button onclick="scan()" class="px-5 py-2 bg-gradient-to-r from-purple-600 to-pink-600 rounded-lg font-bold">TARA</button>
</div>
<p class="text-xs text-purple-400 mt-2">✓ Manganato, MangaDex, Asura | ⚡ Paralel indirme</p>
</div>
<div id="load" class="hidden text-center py-12"><div class="animate-spin h-10 w-10 border-2 border-purple-400 border-t-transparent rounded-full mx-auto mb-2"></div>Taranıyor...</div>
<div id="res" class="hidden bg-slate-900/50 border border-purple-500/30 rounded-xl p-4">
<div class="flex justify-between mb-3"><h2 id="title" class="text-xl font-bold"></h2><button onclick="selAll()" class="text-sm px-3 py-1 bg-purple-600/30 rounded">Tümü</button></div>
<div class="mb-3 flex gap-2 items-center"><span>Seçili: <b id="cnt">0</b></span><button id="dl" onclick="down()" disabled class="px-4 py-1 bg-pink-600 disabled:opacity-40 rounded font-bold">📥 İNDİR</button><span class="text-xs text-yellow-400">Max 2 chapter</span></div>
<div id="chs" class="space-y-1 max-h-80 overflow-y-auto"></div>
</div>
<div id="prog" class="hidden bg-slate-900/50 border border-purple-500/30 rounded-xl p-4 mt-4 text-center">
<div class="font-bold mb-2">İNDİRİLİYOR...</div>
<div id="ptxt" class="text-sm text-purple-300 mb-2"></div>
<div class="bg-slate-800 rounded-full h-2"><div id="pbar" class="h-full bg-gradient-to-r from-purple-600 to-pink-600 rounded-full transition-all" style="width:0"></div></div>
</div>
</div>
<script>
let chs=[],sel=new Set(),ttl='';
async function scan(){
  const u=document.getElementById('url').value.trim();if(!u)return alert('Link girin');
  document.getElementById('load').classList.remove('hidden');document.getElementById('res').classList.add('hidden');
  try{
    const r=await fetch('/api/scrape',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({url:u})});
    const d=await r.json();if(!r.ok||!d.chapters?.length)throw new Error(d.error||'Bulunamadı');
    chs=d.chapters;ttl=d.title;sel.clear();document.getElementById('title').textContent=ttl;render();
    document.getElementById('load').classList.add('hidden');document.getElementById('res').classList.remove('hidden');
  }catch(e){document.getElementById('load').classList.add('hidden');alert(e.message)}
}
function render(){
  const c=document.getElementById('chs');c.innerHTML='';
  chs.forEach((ch,i)=>{const s=sel.has(i);const d=document.createElement('div');
    d.className='p-2 rounded cursor-pointer border '+(s?'bg-purple-600/30 border-purple-400':'bg-slate-800/50 border-slate-700');
    d.onclick=()=>{s?sel.delete(i):sel.add(i);render()};
    d.innerHTML='<span class="text-purple-300">Ch '+ch.number+'</span> - '+ch.title;c.appendChild(d)});
  document.getElementById('cnt').textContent=sel.size;document.getElementById('dl').disabled=sel.size===0;
}
function selAll(){sel.size===chs.length?sel.clear():chs.forEach((_,i)=>sel.add(i));render()}
async function down(){
  if(!sel.size)return;if(sel.size>2&&!confirm('2\'den fazla chapter seçtiniz. Devam?'))return;
  const s=Array.from(sel).map(i=>chs[i]);
  document.getElementById('res').classList.add('hidden');document.getElementById('prog').classList.remove('hidden');
  document.getElementById('ptxt').textContent='PDF hazırlanıyor...';document.getElementById('pbar').style.width='30%';
  try{
    const r=await fetch('/api/download',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({chapters:s,title:ttl})});
    if(!r.ok){const e=await r.json();throw new Error(e.error||'Hata')}
    document.getElementById('pbar').style.width='90%';
    const b=await r.blob();const a=document.createElement('a');a.href=URL.createObjectURL(b);a.download=ttl.replace(/[^a-z0-9]/gi,'_')+'.pdf';a.click();
    document.getElementById('pbar').style.width='100%';document.getElementById('ptxt').textContent='Tamamlandı! ✓';
    setTimeout(()=>{document.getElementById('prog').classList.add('hidden');document.getElementById('res').classList.remove('hidden')},1500);
  }catch(e){alert(e.message);document.getElementById('prog').classList.add('hidden');document.getElementById('res').classList.remove('hidden')}
}
</script></body></html>'''

@app.route('/')
def index():
    return render_template_string(HTML)

@app.route('/api/scrape', methods=['POST'])
def scrape():
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
            return jsonify(r)
        return jsonify({'error': 'Chapter bulunamadı'}), 404
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/download', methods=['POST'])
def download():
    try:
        data = request.json
        chapters = data.get('chapters', [])
        title = data.get('title', 'manga')
        if not chapters:
            return jsonify({'error': 'Chapter seçilmedi'}), 400
        if len(chapters) > 5:
            return jsonify({'error': 'Max 5 chapter'}), 400
        
        print(f"\n=== PDF: {title} ({len(chapters)} ch) ===")
        site = scraper.detect_site(chapters[0].get('url', ''))
        
        pdf_path = os.path.join(tempfile.gettempdir(), f"m{abs(hash(title))%9999}.pdf")
        c = canvas.Canvas(pdf_path, pagesize=A4)
        w, h = A4
        
        # Cover
        c.setFont("Helvetica-Bold", 22)
        c.drawString(40, h-80, title[:50])
        c.setFont("Helvetica", 12)
        c.drawString(40, h-105, f"{len(chapters)} Chapter")
        c.showPage()
        
        total = 0
        for ch in chapters:
            print(f"  Ch {ch.get('number')}: {ch.get('url','')[:50]}")
            c.setFont("Helvetica-Bold", 18)
            c.drawString(40, h-80, f"Chapter {ch.get('number','?')}")
            c.showPage()
            
            imgs = scraper.get_chapter_images(ch.get('url'), site)
            print(f"    {len(imgs)} images found")
            if not imgs:
                continue
            
            downloaded = scraper.download_parallel(imgs, ch.get('url'), workers=6)
            print(f"    {len(downloaded)} downloaded")
            
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
                    pw, ph = w-30, h-30
                    if ratio > ph/pw:
                        nh, nw = ph, ph/ratio
                    else:
                        nw, nh = pw, pw*ratio
                    
                    buf = BytesIO()
                    img.save(buf, 'JPEG', quality=75)
                    buf.seek(0)
                    c.drawImage(ImageReader(buf), (w-nw)/2, (h-nh)/2, nw, nh)
                    c.setFont("Helvetica", 7)
                    c.drawString(w/2-20, 8, f"{ch.get('number')}-{total+1}")
                    c.showPage()
                    total += 1
                except:
                    pass
        
        c.save()
        print(f"  Total: {total} pages\n")
        return send_file(pdf_path, as_attachment=True, download_name=f"{title[:25]}.pdf")
    except Exception as e:
        print(f"Error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/health')
def health():
    return jsonify({'status': 'ok'})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
