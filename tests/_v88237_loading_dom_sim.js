const fs=require('fs'),vm=require('vm'),assert=require('assert');
const script=fs.readFileSync(process.argv[2], 'utf8');
const listeners={}, timers=[];let mutation=null;
class Elem{
 constructor(id,rect={left:0,right:0,top:0,bottom:0,width:0,height:0}){
  this.id=id;this.rect=rect;this.style={};this.attrs={};this.innerHTML='';this.classes=new Set();this.content=[];
  this.classList={add:c=>this.classes.add(c),remove:c=>this.classes.delete(c),contains:c=>this.classes.has(c)};
 }
 getBoundingClientRect(){return this.rect}
 setAttribute(a,b){this.attrs[a]=b}
 querySelectorAll(){return this.content}
 closest(){return null}
 querySelector(){return null}
}
const box=(id,w=10,h=10)=>new Elem(id,{left:0,right:w,top:0,bottom:h,width:w,height:h});
const dict={};
const root=box('root',1000,900),sb=box('sidebar',255,900),main=box('main',1728,900),topbar=box('topbar',1473,123),block=box('block',1473,700);
sb.rect.right=255;topbar.rect.bottom=123;
let mounted=true;
const app=box('app',1000,900);
const found={
 '[data-testid="stMain"]':main,
 '[data-testid="stSidebar"]':sb,
 'div[data-testid="stElementContainer"]:has(.st-key-hr_global_topbar_shell)':topbar,
 '[data-testid="stMainBlockContainer"]':block
};
root.querySelector=()=>mounted?app:null;
block.querySelector=()=>box('title');
block.content=[box('a'),box('b'),box('c')];
dict.root=root;
const doc={head:{appendChild:e=>dict[e.id]=e},body:{appendChild:e=>dict[e.id]=e},
 createElement:t=>new Elem(t),getElementById:id=>dict[id]||null,
 querySelector:q=>found[q]||null,
 addEventListener:(name,cb)=>listeners[name]=cb,removeEventListener:()=>{}
};
const host={document:doc,getComputedStyle:()=>({display:'block',visibility:'visible'}),
 setTimeout:(cb,ms)=>{let e={cb,ms,cleared:false};timers.push(e);return e},clearTimeout:t=>{if(t)t.cleared=true},
 requestAnimationFrame:cb=>cb(),addEventListener:()=>{},removeEventListener:()=>{}};
class MutationObserver { constructor(cb){this.cb=cb;mutation=cb} observe(){} disconnect(){} }
vm.runInNewContext(script,{window:{parent:host},MutationObserver});
const controller=host.__aiHrLoadingTransitionController,overlay=dict['ai-hr-loading-transition'];
assert.equal(controller.version,237);
assert.equal(overlay.style.left,'255px');assert.equal(overlay.style.top,'126px');
const trigger=ms=>{const active=timers.filter(t=>!t.cleared && t.ms===ms);for(const t of active){t.cleared=true;t.cb()}};
const click=(kind)=>listeners.click({defaultPrevented:false,target:{nodeType:1,closest:selector=>{
 if(kind==='sidebar'&&selector.includes('stSidebar'))return {disabled:false};
 if(kind==='quick'&&selector.includes('quick_action_button_'))return {disabled:false};
 if(kind==='notification'&&selector.includes('open_notification_'))return {disabled:false};
 return null;
}}});
// Regular form and chat submit does not produce a full-screen cover.
click('form');assert(!timers.some(t=>t.ms===220&&!t.cleared));
// Sidebar navigation triggers loading; page ready releases.
click('sidebar');trigger(220);assert(overlay.classList.contains('ai-hr-loading-visible'));
controller.ready();trigger(90);assert(!overlay.classList.contains('ai-hr-loading-visible'));
// A quick-action or notification route starts feedback as well.
click('quick');trigger(220);assert(overlay.classList.contains('ai-hr-loading-visible'));
controller.ready();trigger(90);
click('notification');trigger(220);assert(overlay.classList.contains('ai-hr-loading-visible'));
controller.ready();trigger(90);
// Partial rerun empties main but leaves app/sidebar mounted; detect it.
block.content=[];mutation();trigger(45);trigger(70);
assert(overlay.classList.contains('ai-hr-loading-visible'),'partial page blank must be covered');
block.content=[box('new1'),box('new2')];mutation();trigger(170);
assert(!overlay.classList.contains('ai-hr-loading-visible'),'restored main must release overlay');
// Prevent old controller surviving live code upgrade and duplicating listeners.
let replaced=false;const oldVersion=controller.version;
controller.version=236;controller.dispose=()=>{replaced=true;};
vm.runInNewContext(script,{window:{parent:host},MutationObserver});
assert(replaced);assert.equal(host.__aiHrLoadingTransitionController.version,oldVersion);
console.log('PASS: navigation, partial blank, content restored, form excluded, controller version update');
