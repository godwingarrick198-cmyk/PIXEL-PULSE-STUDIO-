const fs = require('fs');
const PptxGenJS = require('pptxgenjs');

const [, , specPath, outputPath, imagePath] = process.argv;
if (!specPath || !outputPath) process.exit(2);
const spec = JSON.parse(fs.readFileSync(specPath, 'utf8'));
const slides = Array.isArray(spec.slides) ? spec.slides : [];
const company = spec.company || 'Company';
const style = String(spec.style || '').toLowerCase();
const image = imagePath && fs.existsSync(imagePath) ? imagePath : null;

const themes = {
  'premium minimal': { bg:'F7F7F5', ink:'171717', muted:'666666', accent:'111827', soft:'E5E7EB' },
  'bold modern': { bg:'0B1020', ink:'F8FAFC', muted:'CBD5E1', accent:'7C3AED', soft:'1E293B' },
  'tech': { bg:'08111F', ink:'F8FAFC', muted:'B8C7D9', accent:'06B6D4', soft:'123047' },
  'creative': { bg:'FFF8F1', ink:'201A17', muted:'6B625C', accent:'F97316', soft:'FFE4D1' },
  'corporate': { bg:'F4F7FB', ink:'102033', muted:'5D6B7A', accent:'2563EB', soft:'DCE8FA' },
  'vibrant': { bg:'FFFDF7', ink:'1F2937', muted:'5B6470', accent:'E11D48', soft:'FFE4EA' }
};
const theme = Object.entries(themes).find(([k]) => style.includes(k))?.[1] || themes['premium minimal'];
const pptx = new PptxGenJS();
pptx.layout='LAYOUT_WIDE';
pptx.author='Pixel Pulse Studio';
pptx.company='Pixel Pulse Studio';
pptx.subject=`${company} presentation`;
pptx.title=`${company} presentation`;
pptx.lang='en-US';
pptx.theme={headFontFace:'Aptos Display',bodyFontFace:'Aptos',lang:'en-US'};
pptx.defineSlideMaster({title:'BASE',background:{color:theme.bg},objects:[
  {rect:{x:0,y:0,w:13.333,h:0.07,fill:{color:theme.accent},line:{color:theme.accent}}},
  {text:{text:company,options:{x:0.62,y:7.12,w:4,h:0.18,fontFace:'Aptos',fontSize:7,color:theme.muted,margin:0}}},
  {text:{text:'PIXEL PULSE STUDIO',options:{x:9.9,y:7.12,w:2.7,h:0.18,fontFace:'Aptos',fontSize:7,color:theme.muted,align:'right',margin:0}}}
]});
function t(slide,text,x,y,w,h,o={}){slide.addText(String(text??''),{x,y,w,h,margin:0,fit:'shrink',fontFace:'Aptos',...o});}
function round(slide,x,y,w,h,fill,line=fill){slide.addShape(pptx.ShapeType.roundRect,{x,y,w,h,fill:{color:fill},line:{color:line,transparency:100}});}
function accent(slide,x,y,w,h=0.07){slide.addShape(pptx.ShapeType.rect,{x,y,w,h,fill:{color:theme.accent},line:{color:theme.accent}});}
function img(slide,x,y,w,h){if(image)slide.addImage({path:image,x,y,w,h});}
function bullets(s){return (Array.isArray(s.bullets)?s.bullets:[]).map(x=>String(x).trim()).filter(Boolean).slice(0,5);}
function list(slide,bs,x,y,w,h,size=17){const runs=(bs.length?bs:['Key point from the supplied brief.']).map((b,i)=>({text:b,options:{bullet:{indent:16},breakLine:i<bs.length-1}}));slide.addText(runs,{x,y,w,h,margin:0.02,fontFace:'Aptos',fontSize:size,color:theme.ink,fit:'shrink',paraSpaceAfterPt:12});}
function title(slide,txt,sub){t(slide,txt,0.68,0.46,11.6,0.62,{fontFace:'Aptos Display',fontSize:27,bold:true,color:theme.ink});if(sub)t(slide,sub,0.7,1.08,10.8,0.28,{fontSize:9.5,color:theme.muted});}
function metric(slide,v,l,x){round(slide,x,1.72,2.72,1.25,theme.soft);t(slide,v,x+0.18,1.9,2.36,0.42,{fontFace:'Aptos Display',fontSize:25,bold:true,color:theme.accent});t(slide,l,x+0.18,2.4,2.36,0.34,{fontSize:9.5,color:theme.muted});}

slides.forEach((s,i)=>{
  const n=i+1,total=slides.length, txt=String(s.title||`Slide ${n}`), bs=bullets(s), layout=String(s.layout||'CONTENT').toUpperCase();
  const slide=pptx.addSlide('BASE');
  t(slide,`${String(n).padStart(2,'0')} / ${String(total).padStart(2,'0')}`,11.55,7.07,0.72,0.18,{fontSize:7,color:theme.muted,align:'right'});
  if(n===1||layout==='TITLE'||layout==='COVER'){
    slide.background={color:theme.accent};
    slide.addShape(pptx.ShapeType.rect,{x:0,y:0,w:13.333,h:7.5,fill:{color:theme.accent},line:{color:theme.accent}});
    if(image){img(slide,8.25,0,5.083,7.5);slide.addShape(pptx.ShapeType.rect,{x:7.72,y:0,w:1,h:7.5,fill:{color:theme.accent,transparency:8},line:{color:theme.accent,transparency:100}});}
    t(slide,company,0.78,0.92,6.8,0.65,{fontFace:'Aptos Display',fontSize:31,bold:true,color:'FFFFFF'});
    t(slide,txt,0.82,1.95,6.45,1.25,{fontFace:'Aptos Display',fontSize:25,bold:true,color:'FFFFFF'});
    t(slide,bs[0]||'A clear, client-ready presentation built by Pixel Pulse Studio.',0.84,5.62,6.15,0.72,{fontSize:14,color:'F1F5F9'});
    t(slide,'PIXEL PULSE STUDIO  /  PRESENTATION',0.84,6.78,5.2,0.22,{fontSize:7.5,bold:true,color:'E2E8F0'});
    return;
  }
  title(slide,txt,`${company}  •  ${n}/${total}`);
  if(layout==='STATS'||/market|traction|result|metric|growth|opportunity/i.test(txt)){
    bs.slice(0,4).forEach((b,j)=>{const p=b.split(':');metric(slide,p.length>1?p[0]:String(j+1),p.length>1?p.slice(1).join(':').trim():b,0.72+j*3.08);});
    list(slide,bs,0.75,3.55,11.6,2.5,14);
  }else if(layout==='TWO_COLUMN'||/solution|offering|benefit|competition|business model|approach/i.test(txt)){
    round(slide,0.7,1.62,5.72,4.8,theme.soft);round(slide,6.82,1.62,5.8,4.8,theme.bg,theme.soft);
    const m=Math.ceil(bs.length/2);t(slide,'WHAT MATTERS',1,1.98,4.6,0.3,{fontSize:9,bold:true,color:theme.accent});list(slide,bs.slice(0,m),1,2.45,4.75,3.55,15);t(slide,'HOW WE MOVE FORWARD',7.12,1.98,4.7,0.3,{fontSize:9,bold:true,color:theme.accent});list(slide,bs.slice(m),7.12,2.45,4.78,3.55,15);
  }else if(layout==='QUOTE'||/vision|mission|key message/i.test(txt)){
    t(slide,'“',0.82,1.62,0.7,0.8,{fontFace:'Georgia',fontSize:44,bold:true,color:theme.accent});t(slide,bs[0]||'A focused message for the audience.',1.48,2.08,10.55,1.65,{fontFace:'Aptos Display',fontSize:25,bold:true,color:theme.ink,italic:true,align:'center',valign:'mid'});accent(slide,5.9,4.25,1.5,0.08);list(slide,bs.slice(1),2,4.72,9.3,1.35,13);
  }else if(layout==='CTA'||/next step|contact|call to action|closing/i.test(txt)){
    slide.addShape(pptx.ShapeType.rect,{x:0.7,y:1.62,w:11.95,h:4.82,fill:{color:theme.accent},line:{color:theme.accent}});t(slide,bs[0]||'Let’s build the next step together.',1.15,2.28,10.9,1.25,{fontFace:'Aptos Display',fontSize:27,bold:true,color:'FFFFFF',align:'center'});list(slide,bs.slice(1),2,4.02,9.3,1.25,13);t(slide,s.email||'Ready to continue',1.2,5.75,10.8,0.32,{fontSize:10,color:'E2E8F0',align:'center'});
  }else{
    const visual=image&&(n%3===0||layout==='IMAGE'||layout==='VISUAL');
    if(visual){round(slide,0.72,1.62,7.1,4.88,theme.bg,theme.soft);list(slide,bs,1,2.02,6.55,4,16);round(slide,8.05,1.62,4.58,4.88,theme.soft);img(slide,8.18,1.75,4.32,4.62);}
    else{accent(slide,0.72,1.72,1.15);list(slide,bs,0.76,2.05,11.35,4,18);}
  }
});
if(!slides.length){const s=pptx.addSlide('BASE');t(s,company,0.8,1.4,11.5,0.7,{fontSize:30,bold:true,color:theme.ink});t(s,'No slide strategy was returned.',0.82,2.4,10,0.5,{fontSize:18,color:theme.muted});}
pptx.writeFile({fileName:outputPath}).catch(e=>{console.error(e);process.exit(1);});
