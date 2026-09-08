"""Contrast audit: every visible text element, in every theme combination.

Run against a locally running copy of the app:

    python -m streamlit run app.py --server.port 8600 &
    python tools/audit_contrast.py 8600

Exits non-zero if any text falls below its WCAG AA floor (4.5:1, or 3.0:1 for
large text). It walks the DOM rather than a list of selectors, because the bug
this exists to catch was text nobody had thought to name: the person radio
labels and the week date kept Streamlit's default rgb(49,51,63), which is fine
on white and 1.68:1 on the dark theme.

Checking by eye does not scale to four theme combinations and forty elements.
This does.
"""
import sys
from playwright.sync_api import sync_playwright

PORT = sys.argv[1] if len(sys.argv) > 1 else "8600"

JS = r"""
() => {
  const lum = (r,g,b) => { const a=[r,g,b].map(v=>{v/=255;
      return v<=0.03928 ? v/12.92 : Math.pow((v+0.055)/1.055,2.4);});
      return 0.2126*a[0]+0.7152*a[1]+0.0722*a[2]; };
  const parse = s => { const m=s.match(/rgba?\(([^)]+)\)/); if(!m) return null;
      const p=m[1].split(',').map(x=>parseFloat(x));
      return {r:p[0],g:p[1],b:p[2],a:p.length>3?p[3]:1}; };
  const effBg = el => { let e=el;
      while(e){ const c=parse(getComputedStyle(e).backgroundColor);
        if(c && c.a>0.5) return c; e=e.parentElement; }
      return {r:255,g:255,b:255,a:1}; };
  const out=[];
  document.querySelectorAll('body *').forEach(el=>{
    if (el.closest('#rmg-fs-bar')) return;              // the control styles itself
    const txt=[...el.childNodes].filter(n=>n.nodeType===3)
                .map(n=>n.textContent.trim()).join(' ').trim();
    if(!txt) return;
    const cs=getComputedStyle(el);
    if(cs.visibility==='hidden'||cs.display==='none'||parseFloat(cs.opacity)===0) return;
    const rect=el.getBoundingClientRect();
    if(rect.width<1||rect.height<1) return;
    const fg=parse(cs.color); if(!fg) return;
    const bg=effBg(el);
    const l1=lum(fg.r,fg.g,fg.b), l2=lum(bg.r,bg.g,bg.b);
    const ratio=(Math.max(l1,l2)+0.05)/(Math.min(l1,l2)+0.05);
    const px=parseFloat(cs.fontSize), bold=parseInt(cs.fontWeight)>=700;
    const large=px>=24||(px>=18.66&&bold);
    out.push({text:txt.slice(0,42), color:cs.color, bg:`rgb(${bg.r}, ${bg.g}, ${bg.b})`,
              ratio:+ratio.toFixed(2), floor: large?3.0:4.5,
              pass: ratio >= (large?3.0:4.5)});
  });
  return out;
}
"""

with sync_playwright() as p:
    b = p.chromium.launch(executable_path="/opt/pw-browsers/chromium-1194/chrome-linux/chrome")
    ctx = b.new_context(viewport={"width":1100,"height":1000})
    pg = ctx.new_page()
    pg.goto(f"http://localhost:{PORT}", wait_until="domcontentloaded")
    pg.wait_for_selector('[data-testid="stExpander"]', timeout=40000); pg.wait_for_timeout(2500)

    total_fail = 0
    for legible, dark in ((0,0),(1,0),(0,1),(1,1)):
        pg.evaluate("""([l,d])=>{localStorage.setItem('rmg-legible',l?'1':'0');
                                 localStorage.setItem('rmg-theme',d?'dark':'light');}""",[legible,dark])
        pg.reload(wait_until="domcontentloaded")
        pg.wait_for_selector('[data-testid="stExpander"]', timeout=40000); pg.wait_for_timeout(2500)
        res = pg.evaluate(JS)
        fails = [r for r in res if not r["pass"]]
        total_fail += len(fails)
        tag = f"legible={legible} dark={dark}"
        print(f"\n=== {tag} ===  {len(res)} text elements, {len(fails)} below AA")
        seen=set()
        for f in fails:
            k=(f["text"],f["color"])
            if k in seen: continue
            seen.add(k)
            print(f"   {f['ratio']:5.2f}:1 (need {f['floor']})  {f['color']:20} on {f['bg']:18} \"{f['text']}\"")
    print(f"\nTOTAL FAILURES ACROSS ALL MODES: {total_fail}")
    b.close()
    sys.exit(1 if total_fail else 0)
