const fs=require('fs'),vm=require('vm'),assert=require('assert');
const script=fs.readFileSync(process.argv[2],'utf8');
const listeners={},timers=[];let mutation=null;
class Elem {
 constructor(id,rect={left:0,right:0,top:0,bottom:0,width:0,height:0}) {
  this.id=id;this.rect=rect;this.style={};this.attrs={};this.innerHTML='';this.classes=new Set();this.content=[];this.isConnected=true;
  this.classList={add:c=>this.classes.add(c),remove:c=>this.classes.delete(c),contains:c=>this.classes.has(c)};
 }
 getBoundingClientRect(){return this.rect}
 setAttribute(a,b){this.attrs[a]=b}
 getAttribute(a){return this.attrs[a]??null}
 querySelectorAll(selector){return this.content}
 closest(selector){return null}
 querySelector(){return null}
}
const box=(id,left,top,right,bottom)=>new Elem(id,{left,top,right,bottom,width:right-left,height:bottom-top});
const dict={};
const root=box('root',0,0,1400,900),sb=box('sidebar',0,0,255,900),main=box('main',255,0,1400,900),topbar=box('topbar',255,0,1400,120),block=box('block',300,130,1380,900);
const app=box('app',0,0,1400,900);
const native=box('tabRoot',330,185,1300,780),bar=box('tabBar',330,190,1300,238),button=box('tab',400,191,535,238),panel=box('panel',330,245,1300,760),label=box('h1',330,270,450,292);
let nativePanelPopulated=true;
button.attrs['aria-selected']='false';
button.closest=selector=> selector.includes('stTabs')?native: null;
native.querySelector=selector=>selector.includes('tab-list')?bar:null;
native.querySelectorAll=selector=>selector.includes('tabpanel')?[panel]:[];
panel.querySelectorAll=()=>nativePanelPopulated?[label]:[];
const segRoot=box('segRoot',340,225,1280,760),segBar=box('segBar',340,225,1280,275),segment=box('seg',390,225,490,275);
segment.attrs['aria-pressed']='false';
segment.closest=selector=>selector.includes('_active_tab')?segRoot:(selector.includes('stSegmentedControl')?segBar:null);
const found={
 '[data-testid="stMain"]':main,
 '[data-testid="stSidebar"]':sb,
 'div[data-testid="stElementContainer"]:has(.st-key-hr_global_topbar_shell)':topbar,
 '[data-testid="stMainBlockContainer"]':block
};
root.querySelector=()=>app;
block.querySelector=()=>box('title',340,270,560,300);
block.content=[box('a',340,250,600,270),box('b',340,290,600,310)];
dict.root=root;
const doc={head:{appendChild:e=>dict[e.id]=e},body:{appendChild:e=>dict[e.id]=e},
 createElement:t=>new Elem(t),getElementById:id=>dict[id]||null,
 querySelector:q=>found[q]||null,
 addEventListener:(name,cb)=>listeners[name]=cb,removeEventListener:()=>{}};
const host={document:doc,innerWidth:1400,innerHeight:900,
 getComputedStyle:()=>({display:'block',visibility:'visible'}),
 setTimeout:(cb,ms)=>{let e={cb,ms,cleared:false};timers.push(e);return e},
 clearTimeout:t=>{if(t)t.cleared=true},
 requestAnimationFrame:cb=>cb(),addEventListener:()=>{},removeEventListener:()=>{}};
class MutationObserver {constructor(cb){this.cb=cb;mutation=cb}observe(){}disconnect(){}}
vm.runInNewContext(script,{window:{parent:host},MutationObserver});
const ctr=host.__aiHrLoadingTransitionController;
const tabOverlay=dict['ai-hr-horizontal-tab-loading'], full=dict['ai-hr-loading-transition'];
assert.equal(ctr.version,238);
const fire=(ms)=>{const queue=timers.filter(t=>!t.cleared && t.ms===ms);for(const t of queue){t.cleared=true;t.cb()}};
const target=(kind)=>({nodeType:1,closest:selector=>{
 if(kind==='native'&&selector.includes('stTabs'))return button;
 if(kind==='seg'&&selector.includes('stSegmentedControl'))return segment;
 if(kind==='sidebar'&&selector.includes('stSidebar'))return {disabled:false};
 return null;
}});
const click=kind=>listeners.click({defaultPrevented:false,target:target(kind)});
// Native tab switching, with delayed content, only covers content BELOW the bar.
click('native');assert(!tabOverlay.classList.contains('ai-hr-loading-visible'));
fire(125);assert(tabOverlay.classList.contains('ai-hr-loading-visible'));
assert.equal(tabOverlay.style.top,'243px');assert.equal(tabOverlay.style.left,'330px');assert.equal(tabOverlay.style.width,'970px');
assert(!full.classList.contains('ai-hr-loading-visible'));
// No global workspace loader even if main content briefly disappears.
block.content=[];mutation();fire(45);fire(70);assert(!full.classList.contains('ai-hr-loading-visible'));
// Completion: new selected tab is populated; suppress overlay.
button.attrs['aria-selected']='true';nativePanelPopulated=true;mutation();fire(105);
assert(!tabOverlay.classList.contains('ai-hr-loading-visible'));
block.content=[box('a2',340,250,600,270),box('b2',340,290,600,310)];
// Fast native switch (within 105ms) never displays skeleton.
button.attrs['aria-selected']='false';click('native');button.attrs['aria-selected']='true';mutation();fire(105);fire(125);
assert(!tabOverlay.classList.contains('ai-hr-loading-visible'));
// Clicking already active tab should not launch loading.
const before=timers.length;click('native');assert.equal(timers.length,before);
// Project-owned segmented tab bar receives scoped loading too.
click('seg');fire(125);assert(tabOverlay.classList.contains('ai-hr-loading-visible'));
assert.equal(tabOverlay.style.top,'280px');
segment.attrs['aria-pressed']='true';ctr.ready();fire(90);assert(!tabOverlay.classList.contains('ai-hr-loading-visible'));
// Sidebar replaces tab state with whole-workspace loading, and no double overlay.
button.attrs['aria-selected']='false';click('native');fire(125);assert(tabOverlay.classList.contains('ai-hr-loading-visible'));
click('sidebar');assert(!tabOverlay.classList.contains('ai-hr-loading-visible'));
fire(220);assert(full.classList.contains('ai-hr-loading-visible'));
ctr.ready();fire(90);
// Plain input/form click never launches a tab loader.
click('form');fire(125);assert(!tabOverlay.classList.contains('ai-hr-loading-visible'));
console.log('PASS: native tabs, segmented tabs, delayed/fast selection, ready, workspace gap, sidebar, form exclusion');
