(() => {
 'use strict';
 const config=JSON.parse(document.getElementById('library-config').textContent);
 const papers=Array.from(document.querySelectorAll('[data-paper]'));
 const metadata=new Map(config.papers.map(p=>[p.id,p]));
 const readPrefix='mental_modeling.read.v1.',notePrefix='mental_modeling.notes.v2.';
 const memory=new Map();let unavailable=false,timer,undoAction=null,expanded=false;
 const params=new URLSearchParams(location.search);
 let state=params.get('state')==='read'?'read':'unread';
 let group=['main','family','ai'].includes(params.get('group'))?params.get('group'):'all';
 const search=document.getElementById('search'),topic=document.getElementById('topic-filter'),sort=document.getElementById('sort');
 search.value=params.get('q')||'';
 if(Array.from(topic.options).some(x=>x.value===params.get('topic')))topic.value=params.get('topic');
 const get=key=>{if(memory.has(key))return memory.get(key);try{return localStorage.getItem(key);}catch(_){unavailable=true;return null;}};
 function put(key,value){memory.set(key,value);try{localStorage.setItem(key,value);return true;}catch(_){unavailable=true;return false;}}
 const read=id=>get(readPrefix+id)==='1';
 const normalize=text=>text.normalize('NFKC').toLocaleLowerCase().replace(/\s+/g,' ').trim();
 function notice(message,action=null){
  clearTimeout(timer);undoAction=action;const box=document.getElementById('notice');
  box.querySelector('span').textContent=message+(unavailable?'。浏览器无法保存，当前操作仅在本页有效，请导出备份。':'');
  document.getElementById('undo').hidden=!action;box.hidden=false;
  if(!unavailable)timer=setTimeout(()=>{box.hidden=true;undoAction=null;},7000);
 }
 function updateUrl(){
  const p=new URLSearchParams();
  if(state==='read')p.set('state',state);if(group!=='all')p.set('group',group);
  if(search.value)p.set('q',search.value);if(topic.value!=='all')p.set('topic',topic.value);
  try{history.replaceState(null,'',location.pathname+(p.size?'?'+p:'')+location.hash);}catch(_){}
 }
 function render(){
  document.getElementById('group-filter').value=group;
  const terms=normalize(search.value).split(' ').filter(Boolean),counts={all:0,main:0,family:0,ai:0};let readTotal=0,shown=0;
  papers.forEach(p=>{
   const id=p.dataset.id,isRead=read(id);if(isRead)readTotal++;
   const button=p.querySelector('.mark-read');button.disabled=false;button.setAttribute('aria-pressed',String(isRead));
   const label=isRead?'移回没看过':'标记看过';button.title=label;button.setAttribute('aria-label',label+'：'+metadata.get(id).title_zh);button.querySelector('span').textContent=isRead?'已看过':'标记看过';
   const text=normalize(p.dataset.search+' '+(get(notePrefix+id)||''));
   const matches=(state==='read')===isRead&&(topic.value==='all'||p.dataset.topic===topic.value)&&terms.every(t=>text.includes(t));
   if(matches){counts.all++;counts[p.dataset.group]++;}
   p.hidden=!matches||(group!=='all'&&p.dataset.group!==group);if(!p.hidden)shown++;
  });
  document.getElementById('read-count').textContent=readTotal;document.getElementById('unread-count').textContent=papers.length-readTotal;
  document.querySelectorAll('[data-state]').forEach(b=>{b.classList.toggle('active',b.dataset.state===state);b.setAttribute('aria-pressed',String(b.dataset.state===state));});
  document.querySelectorAll('[data-group-filter]').forEach(b=>{b.classList.toggle('active',b.dataset.groupFilter===group);b.setAttribute('aria-pressed',String(b.dataset.groupFilter===group));});
  document.querySelectorAll('[data-nav-count]').forEach(n=>n.textContent=counts[n.dataset.navCount]);
  document.querySelectorAll('[data-section]').forEach(s=>{const key=s.dataset.section;s.hidden=(group!=='all'&&group!==key)||counts[key]===0;s.querySelector('[data-group-count]').textContent=counts[key];});
  const label=state==='read'?'看过':'没看过';document.getElementById('crumb-state').textContent=label;document.getElementById('view-label').textContent=label;
  document.getElementById('view-help').textContent=state==='read'?'回看读过的研究和留下的想法，也可以移回「没看过」再读。':'把感兴趣的研究留在这里，读完一篇，勾选移入「看过」。';
  document.getElementById('view-count').textContent=state==='read'?readTotal:papers.length-readTotal;
  const filtered=!!terms.length||topic.value!=='all'||group!=='all';
  document.getElementById('results-text').textContent=(filtered?'筛选结果':'当前'+label)+' · '+shown+' 篇';document.getElementById('clear-filters').hidden=!filtered;
  document.getElementById('empty-state').hidden=shown!==0;
  document.getElementById('empty-title').textContent=filtered?'没有找到匹配的文献':state==='read'?'还没有看过的论文':'这一份文献，已经读完了';
  document.getElementById('empty-description').textContent=filtered?'试试缩短关键词，或切换研究方向与来源分类。':state==='read'?'读完一篇后，点击「标记看过」，就会收进这里。':'可以回看笔记，或等待新的研究加入文献库。';
  document.getElementById('empty-action').textContent=filtered?'清除筛选':state==='read'?'去没看过的文献':'回看已读文献';updateUrl();
 }
 function reset(){search.value='';topic.value='all';group='all';render();}
 function order(){document.querySelectorAll('.paper-list').forEach(list=>Array.from(list.children).sort((a,b)=>{const key=sort.value==='added'?'added':'date';const value=a.dataset[key].localeCompare(b.dataset[key]);return(sort.value==='oldest'?value:-value)||a.id.localeCompare(b.id);}).forEach(p=>list.appendChild(p)));}
 papers.forEach(p=>{
  const id=p.dataset.id,button=p.querySelector('.mark-read'),textarea=p.querySelector('textarea'),badge=p.querySelector('.has-note');
  textarea.value=get(notePrefix+id)||'';badge.hidden=!textarea.value.trim();
  button.addEventListener('click',()=>{
   const before=read(id);put(readPrefix+id,before?'0':'1');const title=metadata.get(id).title_zh;
   const visible=papers.filter(p=>!p.hidden),index=visible.indexOf(p),next=visible[index+1]||visible[index-1];render();
   const focusTarget=next&&!next.hidden?next.querySelector('.mark-read'):document.querySelector('[data-state="'+state+'"]');focusTarget.focus({preventScroll:true});
   notice((before?'已移回没看过：':'已移入看过：')+title,()=>{put(readPrefix+id,before?'1':'0');render();if(!p.hidden)button.focus({preventScroll:true});notice('已撤销阅读标记');});
  });
  textarea.addEventListener('input',()=>{const saved=put(notePrefix+id,textarea.value);badge.hidden=!textarea.value.trim();p.querySelector('.note-saved').textContent=saved?'已保存到此浏览器':'未能持久保存，请导出笔记备份';if(!saved)notice('备注暂存在当前页面');});
 });
 document.querySelectorAll('[data-state]').forEach(b=>b.addEventListener('click',()=>{state=b.dataset.state;render();}));
 document.querySelectorAll('[data-group-filter]').forEach(b=>b.addEventListener('click',()=>{group=b.dataset.groupFilter;render();}));
 document.getElementById('group-filter').addEventListener('change',e=>{group=e.target.value;render();});
 document.getElementById('import-button').addEventListener('click',()=>document.getElementById('import-reading').click());
 search.addEventListener('input',render);topic.addEventListener('change',render);sort.addEventListener('change',order);
 document.getElementById('clear-filters').addEventListener('click',reset);
 document.getElementById('empty-action').addEventListener('click',()=>{if(search.value||topic.value!=='all'||group!=='all')reset();else{state=state==='read'?'unread':'read';render();}});
 document.getElementById('expand-notes').addEventListener('click',e=>{expanded=!expanded;papers.filter(p=>!p.hidden).forEach(p=>p.querySelector('details').open=expanded);e.currentTarget.textContent=expanded?'收起研究笔记':'展开研究笔记';e.currentTarget.setAttribute('aria-pressed',String(expanded));});
 document.getElementById('undo').addEventListener('click',()=>undoAction?.());
 document.addEventListener('keydown',e=>{if(e.key==='/'&&!/INPUT|TEXTAREA|SELECT/.test(document.activeElement.tagName)&&!e.ctrlKey&&!e.metaKey){e.preventDefault();search.focus();}});
 function refreshStorage(){memory.clear();papers.forEach(p=>{const t=p.querySelector('textarea');if(document.activeElement!==t)t.value=get(notePrefix+p.dataset.id)||'';p.querySelector('.has-note').hidden=!t.value.trim();});render();}
 window.addEventListener('storage',e=>{if(!e.key||e.key.startsWith(readPrefix)||e.key.startsWith(notePrefix))refreshStorage();});
 window.addEventListener('pageshow',e=>{if(e.persisted)refreshStorage();});
 document.getElementById('export-reading').addEventListener('click',()=>{
  const data={format:'mental-modeling-notes',version:1,exported_at:new Date().toISOString(),papers:config.papers.map(p=>({...p,read:read(p.id),note:get(notePrefix+p.id)||''}))};
  const url=URL.createObjectURL(new Blob([JSON.stringify(data,null,2)],{type:'application/json'}));const a=document.createElement('a');a.href=url;a.download='mental-modeling-notes-'+new Date().toISOString().slice(0,10)+'.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);notice('已导出阅读状态与备注');
 });
 document.getElementById('import-reading').addEventListener('change',async e=>{
  const file=e.target.files?.[0];if(!file)return;
  try{
   if(file.size>8_000_000)throw new Error('文件过大');const data=JSON.parse(await file.text());
   if(data.format!=='mental-modeling-notes'||data.version!==1||!Array.isArray(data.papers))throw new Error('不是本网站的笔记备份');
   const rows=data.papers.filter(p=>metadata.has(p?.id));
   if(rows.some(p=>typeof p.read!=='boolean'||typeof p.note!=='string'||p.note.length>12000))throw new Error('备份内容格式不正确');
   rows.forEach(p=>{if(p.read)put(readPrefix+p.id,'1');if(p.note&&!get(notePrefix+p.id))put(notePrefix+p.id,p.note);});
   papers.forEach(p=>{p.querySelector('textarea').value=get(notePrefix+p.dataset.id)||'';p.querySelector('.has-note').hidden=!p.querySelector('textarea').value.trim();});render();notice('已合并 '+rows.length+' 篇的阅读记录；现有备注已保留');
  }catch(ex){notice('导入失败：'+ex.message);}finally{e.target.value='';}
 });
 order();render();if(unavailable)notice('浏览器无法读取保存记录');
})();
