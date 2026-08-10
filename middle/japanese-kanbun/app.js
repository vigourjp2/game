(()=>{
'use strict';
const $=s=>document.querySelector(s), $$=s=>[...document.querySelectorAll(s)];
const META={id:'middle-kanbun',name:'中学 国語・漢文'};
const FIXED_USER='gakushu-main';
const BEST_KEY='periodicTestBest:'+META.id;
const STATE_KEY='kanbunDungeonState:v1';
let soundOn=true, currentMode=null, deck=[], qIndex=0, score=0, streak=0, maxStreak=0, mistakes=[], answered=false;
const state=loadState(); streak=state.streak||0;

const markQuestions=[
 {q:'連続した2字で、下の字を先に読んで「1字だけ」上へ返るときは？',a:'レ点',o:['一・二点','上・下点','送り仮名'],e:'レ点は「1字返る」ための返り点。'},
 {q:'2字以上隔てて、下から上へ返るときに使うのは？',a:'一・二（・三…）点',o:['レ点','上・下点だけ','句読点'],e:'一二点は、2字以上隔てた戻りを作る。'},
 {q:'一・二点が付いている部分を挟んで、さらに大きく返るときに使うのは？',a:'上・中・下点',o:['レ点だけ','送り仮名','ルビ'],e:'上下点は、一二点を挟むさらに大きな戻りで使う。'},
 {q:'返り点の主な目的は？',a:'漢文を日本語の語順に合わせて読むため',o:['漢字を大きく見せるため','意味を英語に訳すため','句読点を消すため'],e:'返り点は、漢文を日本語の語順で訓読するための符号。'},
 {q:'一二点と上下点が同時にあるとき、先に処理するのは？',a:'一二点',o:['上下点','句点','どちらでも同じ'],e:'内側の一二点を先に読み、そのあと外側の上下点へ。'},
 {q:'「一字返る」か「二字以上返る」かを見分けるのは、何を選ぶ手掛かり？',a:'返り点の種類',o:['漢字の画数','送り仮名の色','句読点の数'],e:'1字ならレ点、2字以上なら一二点が基本。'},
 {q:'レ点が付いた漢字は、最初にどうする？',a:'いったん飛ばして下の字を読む',o:['必ず最初に読む','読まないで削除する','音読みだけする'],e:'レ点付きの字はいったん保留し、直下の字を読んでから戻る。'},
 {q:'「一点」と「レ点」が組み合わさった返り点を見ても、基本の考え方は？',a:'小さい戻りを処理してから大きい戻り',o:['全部逆から読む','返り点を無視する','必ず上からだけ読む'],e:'複合返り点も、レ点の1字戻り→一二点などの大きい戻り、と分解するとよい。'},
 {q:'返り点が無い部分の基本の進み方は？',a:'上から下へ順に読む',o:['下から上へ読む','右から左へ一字ずつ飛ばす','好きな順に読む'],e:'まず上から下へ進み、返り点で必要なときだけ戻る。'},
 {q:'「二字以上隔てて返る」説明に最も合う返り点は？',a:'二点と一点',o:['レ点1個だけ','送り仮名','ふりがな'],e:'一二点は「一点まで進み、二点へ戻る」形を作る。'},
 {q:'上・中・下点が必要になるのは、どんなとき？',a:'一二点の範囲をまたいでさらに返るとき',o:['1字だけ返るとき','送り仮名を書くとき','現代仮名遣いに直すとき'],e:'大きな入れ子の戻りを区別するために上下点を使う。'},
 {q:'返り点を読むときの安全な手順は？',a:'上から進み、付いた字を保留し、合図で戻る',o:['全部の字を逆順にする','音読みしてから考える','送り仮名だけ先に読む'],e:'「上から進む→保留→戻る」が安定。'}
];

const okuriQuestions=[
 {q:'漢文の送り仮名は、基本的にどの文字で付ける？',a:'カタカナ',o:['ひらがな','ローマ字','数字'],e:'訓点の送り仮名はカタカナで付ける。'},
 {q:'送り仮名を付ける基本位置は？',a:'漢字の右下',o:['漢字の左上','行の一番上','漢字の真上'],e:'教科書の基本では、漢字の右下に小さく付ける。'},
 {q:'送り仮名は何のために補う？',a:'漢文を日本語として読むため',o:['漢字の意味を英訳するため','字数を増やすため','書き順を示すため'],e:'日本語として訓読するのに必要な語尾・助詞などを補う。'},
 {q:'送り仮名を付けるときに従うものは？',a:'古典文法の規則',o:['英語文法','数学の公式','現代口語だけ'],e:'古典文法の規則に従う。'},
 {q:'仮名遣いは、教科書の基本では何に従う？',a:'歴史的仮名遣い',o:['現代仮名遣いだけ','ローマ字表記','外来語表記'],e:'古典文法と歴史的仮名遣いに従う。'},
 {q:'送り仮名として補う代表例に入るのは？',a:'用言の活用語尾',o:['漢字の部首名','ページ番号','返り点の番号'],e:'動詞・形容詞などの活用語尾は重要な送り仮名。'},
 {q:'送り仮名として補う代表例に入るのは？',a:'助詞・助動詞',o:['英単語','漢字の画数','句読点の名称'],e:'日本語の文として必要な助詞・助動詞も補う。'},
 {q:'「日本語らしく読むために必要なものを付ける」という説明は何のルール？',a:'送り仮名',o:['レ点','句読点','ルビ'],e:'送り仮名は日本語として成立させるために必要な部分を補う。'},
 {q:'次の漢文を「知らず」と読むとき、「ズ」は何に当たる？',a:'送り仮名',o:['返り点','ふりがな','句点'],e:'「ズ」は日本語として読むために補う送り仮名。',kanbun:{chars:['不','知'],marks:['レ',''],okuri:['ズ','']}},
 {q:'次の漢文を「行ふべし」と読むとき、「フ」「ベシ」のような部分は？',a:'送り仮名',o:['返り点','漢字本文','読み順番号'],e:'活用や助動詞に当たる部分を送り仮名として補う。',kanbun:{chars:['可','行'],marks:['レ','']}},
 {q:'送り仮名と返り点の役割の組み合わせで正しいのは？',a:'送り仮名＝日本語の形を補う／返り点＝読む順を示す',o:['どちらも読む順だけ示す','どちらも意味だけ訳す','役割は完全に同じ'],e:'送り仮名は語形、返り点は語順を主に補助する。'},
 {q:'送り仮名を付けるとき、不要なものまで自由に足してよい？',a:'必要なものを付ける',o:['好きなだけ足す','必ず3文字足す','全漢字に同じ仮名を付ける'],e:'日本語として読むために必要なものを選ぶ。'}
];

const orderProblems=[
 {title:'レ点・基本',chars:['不','知'],marks:['レ',''],target:[1,0],reading:'知 → 不',ex:'レ点は1字だけ返る。まず「知」、それから「不」。'},
 {title:'レ点・基本',chars:['有','志'],marks:['レ',''],target:[1,0],reading:'志 → 有',ex:'上の「有」をいったん保留し、「志」を読んでから戻る。'},
 {title:'レ点・基本',chars:['欲','学'],marks:['レ',''],target:[1,0],reading:'学 → 欲',ex:'レ点なので直下を先に読む。'},
 {title:'レ点・基本',chars:['可','行'],marks:['レ',''],target:[1,0],reading:'行 → 可',ex:'「行」を読んで1字上の「可」に戻る。'},
 {title:'レ点・連続',chars:['不','得','忘'],marks:['レ','レ',''],target:[2,1,0],reading:'忘 → 得 → 不',ex:'レ点が連続しているので、小さな戻りを順に処理すると結果は下から上。'},
 {title:'一二点',chars:['甲','乙','丙'],marks:['二','','一'],target:[1,2,0],reading:'乙 → 丙 → 甲',ex:'「二」の字は保留。「一」まで進んだら「二」へ戻る。'},
 {title:'一二点',chars:['天','地','人','心'],marks:['二','','','一'],target:[1,2,3,0],reading:'地 → 人 → 心 → 天',ex:'2字以上隔てる戻りなので一二点。'},
 {title:'一二点＋レ点',chars:['甲','乙','丙','丁'],marks:['二','レ','','一'],target:[2,1,3,0],reading:'丙 → 乙 → 丁 → 甲',ex:'まず乙のレ点で「丙→乙」。一点まで進んだら二点の甲へ戻る。'},
 {title:'写真の例題',chars:['勿','以','悪','小','為','之'],marks:['下','二','','一','上レ',''],target:[2,3,1,5,4,0],reading:'悪 → 小 → 以 → 之 → 為 → 勿',ex:'写真の番号は 6・3・1・2・5・4。読む順は「悪→小→以→之→為→勿」。'},
 {title:'レ点・反射神経',chars:['未','見'],marks:['レ',''],target:[1,0],reading:'見 → 未',ex:'1字返る形。'},
 {title:'一二点・4字',chars:['春','夏','秋','冬'],marks:['二','','','一'],target:[1,2,3,0],reading:'夏 → 秋 → 冬 → 春',ex:'「一」まで上から進み、そこで「二」に戻る。'},
 {title:'レ点・3連',chars:['甲','乙','丙','丁'],marks:['レ','レ','レ',''],target:[3,2,1,0],reading:'丁 → 丙 → 乙 → 甲',ex:'レ点の連続は、直下を読んで1字戻る操作が連なる。'}
];

const examExtra=[
 {q:'次の写真例の漢文で、最初に読む字は？',a:'悪',o:['勿','以','為'],e:'写真の読み順番号「1」は悪。',kanbun:{chars:['勿','以','悪','小','為','之'],marks:['下','二','','一','上レ','']}},
 {q:'次の写真例の漢文で、2番目に読む字は？',a:'小',o:['以','之','勿'],e:'読む順は 悪→小→以→之→為→勿。',kanbun:{chars:['勿','以','悪','小','為','之'],marks:['下','二','','一','上レ','']}},
 {q:'次の写真例の漢文で、最後に読む字は？',a:'勿',o:['為','之','以'],e:'「勿」が6番目。',kanbun:{chars:['勿','以','悪','小','為','之'],marks:['下','二','','一','上レ','']}},
 {q:'次の写真例の漢文で、3番目に読む字は？',a:'以',o:['悪','為','勿'],e:'3番目は「以」。',kanbun:{chars:['勿','以','悪','小','為','之'],marks:['下','二','','一','上レ','']}},
 {q:'次の写真例の漢文で、4番目に読む字は？',a:'之',o:['小','為','勿'],e:'4番目は「之」。',kanbun:{chars:['勿','以','悪','小','為','之'],marks:['下','二','','一','上レ','']}},
 {q:'返り点で一番小さい戻りの基本単位は？',a:'1字戻るレ点',o:['3字戻る上下点','送り仮名','句点'],e:'レ点は隣り合う2字で1字返る。'},
 {q:'次の漢文の読む順として正しいものは？',a:'知 → 不',o:['不 → 知','不だけ読む','知だけ読む'],e:'レ点なので直下の知を先に読む。',kanbun:{chars:['不','知'],marks:['レ','']}},
 {q:'次の漢文の読む順は？',a:'乙 → 丙 → 甲',o:['甲 → 乙 → 丙','丙 → 乙 → 甲','乙 → 甲 → 丙'],e:'二の甲を保留し、一の丙まで進んで甲へ戻る。',kanbun:{chars:['甲','乙','丙'],marks:['二','','一']}},
 {q:'レ点付きの字を見つけた直後の操作は？',a:'その字を保留して直下へ進む',o:['必ずそこで終了','その字を2回読む','下の字を削除'],e:'レ点は直下→上の字。'},
 {q:'「送り仮名＝カタカナ」は正しい？',a:'正しい',o:['誤り。ひらがなだけ','誤り。数字','誤り。英字'],e:'漢文の訓点ではカタカナで送る。'},
 {q:'1字だけ上へ返る返り点は？',a:'レ点',o:['一・二点','上・下点','送り仮名'],e:'1字だけ返るのがレ点。'},
 {q:'2字以上隔てて返るときの基本は？',a:'一・二点',o:['レ点だけ','送り仮名','句読点'],e:'2字以上隔てるときは一二点を使う。'},
 {q:'送り仮名を付ける位置として正しいのは？',a:'漢字の右下',o:['漢字の左上','本文の欄外だけ','ページ最下部'],e:'基本位置は漢字の右下。'},
 {q:'送り仮名の仮名遣いは何を基本にする？',a:'歴史的仮名遣い',o:['現代仮名遣いだけ','ローマ字','英語式'],e:'古典文法と歴史的仮名遣いに従う。'},
 {q:'次の写真例の漢文で、5番目に読む字は？',a:'為',o:['之','以','勿'],e:'5番目は「為」。',kanbun:{chars:['勿','以','悪','小','為','之'],marks:['下','二','','一','上レ','']}},
 {q:'次の写真例の漢文の読む順として正しいものは？',a:'悪 → 小 → 以 → 之 → 為 → 勿',o:['勿 → 以 → 悪 → 小 → 為 → 之','悪 → 以 → 小 → 為 → 之 → 勿','之 → 為 → 小 → 悪 → 以 → 勿'],e:'写真の番号1〜6を追うと、悪→小→以→之→為→勿。',kanbun:{chars:['勿','以','悪','小','為','之'],marks:['下','二','','一','上レ','']}},
 {q:'次の漢文の読む順は？',a:'志 → 有',o:['有 → 志','有だけ','志だけ'],e:'レ点なので「志」を先に読み、「有」へ戻る。',kanbun:{chars:['有','志'],marks:['レ','']}},
 {q:'一二点と上下点が併用されたときの順序は？',a:'一二点を先に処理してから上下点',o:['上下点を先にする','どちらも無視する','必ず全文を逆順にする'],e:'まず内側の一二点、次に外側の上下点。'}
];

function loadState(){try{return JSON.parse(localStorage.getItem(STATE_KEY)||'{}')}catch{return {}}}
function saveState(){state.streak=streak;state.lastMode=currentMode;localStorage.setItem(STATE_KEY,JSON.stringify(state));updatePersistentUI()}
function updatePersistentUI(){const b=localStorage.getItem(BEST_KEY);$('#bestMini').textContent=b==null?'最高 --点':`最高 ${b}点`;$('#streakStat').innerHTML=`🔥 連続正解 <b>${streak}</b>`}
function shuffle(a){const b=[...a];for(let i=b.length-1;i>0;i--){const j=Math.floor(Math.random()*(i+1));[b[i],b[j]]=[b[j],b[i]]}return b}
function esc(s){return String(s).replace(/[&<>'"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c]))}
function kanbunMarkup(k,{interactive=false}={}){if(!k||!Array.isArray(k.chars))return '';const marks=k.marks||[],okuri=k.okuri||[];return `<div class="kanbunColumn">${k.chars.map((c,i)=>`${interactive?`<button class="kanCell pick" type="button" data-i="${i}" aria-label="${esc(c)}">`:`<span class="kanCell static">`}<span class="kanChar">${esc(c)}</span>${marks[i]?`<small class="kanMark${String(marks[i]).length>1?' combo':''}">${esc(marks[i])}</small>`:''}${okuri[i]?`<small class="kanOkuri">${esc(okuri[i])}</small>`:''}${interactive?'</button>':'</span>'}`).join('')}</div>`}
function showPanel(id){$$('.panel').forEach(x=>x.classList.remove('active'));if(id)$('#'+id).classList.add('active');window.scrollTo({top:id?$('#'+id).offsetTop-70:0,behavior:'smooth'})}
function returnMenu(){currentMode=null;showPanel(null);$('#modeGrid').scrollIntoView({behavior:'smooth',block:'start'})}

$$('[data-mode]').forEach(b=>b.addEventListener('click',()=>startMode(b.dataset.mode)));
$$('[data-back]').forEach(b=>b.addEventListener('click',returnMenu));
$('#lessonToOrder').addEventListener('click',()=>startMode('order'));$('#lessonToExam').addEventListener('click',()=>startMode('exam'));
$('#soundBtn').addEventListener('click',()=>{soundOn=!soundOn;$('#soundBtn').textContent=soundOn?'🔊 ON':'🔇 OFF'});
$('#closeHelp').addEventListener('click',()=>$('#helpModal').classList.remove('show'));$('#helpModal').addEventListener('click',e=>{if(e.target===e.currentTarget)e.currentTarget.classList.remove('show')});

function startMode(mode){currentMode=mode;answered=false;mistakes=[];score=0;maxStreak=streak;
 if(mode==='lesson'){showPanel('lessonPanel');return}
 if(mode==='marks')deck=shuffle(markQuestions).slice(0,10).map(q=>({...q,type:'mc'}));
 if(mode==='okuri')deck=shuffle(okuriQuestions).slice(0,10).map(q=>({...q,type:'mc'}));
 if(mode==='order')deck=shuffle(orderProblems).slice(0,10).map(q=>({...q,type:'order'}));
 if(mode==='exam'){
   const mc=[...markQuestions,...okuriQuestions,...examExtra].map(q=>({...q,type:'mc'}));
   const ord=orderProblems.map(q=>({...q,type:'order'}));
   const mixed=[]; while(mixed.length<50){mixed.push(...shuffle([...mc,...ord]));} deck=shuffle(mixed).slice(0,50);
 }
 qIndex=0;showPanel('gamePanel');$('#resultArea').classList.remove('show');$('#questionArea').style.display='block';renderQuestion();
}
function modeName(){return ({marks:'🎯 返り点ハント',okuri:'✍️ 送り仮名道場',order:'🧩 読み順バトル',exam:'🔥 定期テスト決戦'})[currentMode]||'ゲーム'}
function pointsPer(){return currentMode==='exam'?2:10}
function renderHUD(){const total=deck.length;$('#roundTitle').textContent=modeName();$('#qNo').textContent=`${Math.min(qIndex+1,total)} / ${total}`;$('#scoreHud').textContent=`${score}点`;$('#streakHud').textContent=`🔥 ${streak}`;$('#progressBar').style.width=`${(qIndex/total)*100}%`}
function renderQuestion(){answered=false;renderHUD();const q=deck[qIndex];if(!q){finish();return}if(q.type==='order')renderOrder(q);else renderMC(q)}
function renderMC(q){const opts=shuffle([q.a,...q.o.filter(x=>x!==q.a)]).slice(0,4);const preview=q.kanbun?`<div class="mcKanbun"><div class="verticalLabel">上から下へ読む漢文</div>${kanbunMarkup(q.kanbun)}</div>`:'';$('#questionArea').innerHTML=`
 <span class="promptTag">${currentMode==='okuri'?'送り仮名':'返り点・基本'}</span>
 <div class="question">${esc(q.q)}</div>${preview}<div class="sub">正しいものを1つ選べ。</div>
 <div class="choices">${opts.map((o,i)=>`<button class="choice" data-answer="${esc(o)}"><span style="color:#9a3412">${'ABCD'[i]}.</span> ${esc(o)}</button>`).join('')}</div>
 <div class="feedback" id="feedback"></div>
 <div class="actions"><button class="btn primary" id="nextBtn" disabled>次へ →</button><button class="btn ghost" id="helpBtn">ヒント</button><button class="btn ghost" id="menuBtn">メニュー</button></div>`;
 $$('.choice').forEach(b=>b.addEventListener('click',()=>answerMC(b,b.dataset.answer,q)));$('#nextBtn').addEventListener('click',next);$('#helpBtn').addEventListener('click',()=>$('#helpModal').classList.add('show'));$('#menuBtn').addEventListener('click',returnMenu)}
function answerMC(btn,val,q){if(answered)return;answered=true;const ok=val===q.a;$$('.choice').forEach(b=>{b.disabled=true;if(b.dataset.answer===q.a)b.classList.add('correct')});if(!ok)btn.classList.add('wrong');settle(ok,q.e,`${q.q} → ${q.a}`)}
function renderOrder(q){let picked=[],hadError=false;$('#questionArea').innerHTML=`
 <span class="promptTag">${esc(q.title)}</span><div class="question">日本語として読む順に、漢字をタップ。</div><div class="sub">本文は教科書と同じ<b>縦書き</b>。上から下へ見て、返り点に従い1番目から選べ。</div>
 <div class="verticalCard"><div class="verticalLabel">漢文本文｜上 → 下</div><div class="kanbunStage" id="kanbunLine">${kanbunMarkup({chars:q.chars,marks:q.marks}, {interactive:true})}</div><div class="orderTray" id="orderTray"><span class="sub">ここに読む順が並ぶ</span></div></div>
 <div class="feedback" id="feedback"></div>
 <div class="actions"><button class="btn primary" id="nextBtn" disabled>次へ →</button><button class="btn ghost" id="resetOrder">やり直す</button><button class="btn ghost" id="menuBtn">メニュー</button></div>`;
 const cells=$$('.kanbunStage .kanCell');
 function draw(){const tray=$('#orderTray');tray.innerHTML=picked.length?picked.map((ix,n)=>`<span class="orderChip">${n+1}. ${esc(q.chars[ix])}</span>${n<picked.length-1?'<span class="orderArrow">→</span>':''}`).join(''):'<span class="sub">ここに読む順が並ぶ</span>';cells.forEach((c,i)=>{c.classList.toggle('done',picked.includes(i));const old=c.querySelector('.kanNum');if(old)old.remove();const n=picked.indexOf(i);if(n>=0)c.insertAdjacentHTML('beforeend',`<b class="kanNum">${n+1}</b>`)})}
 cells.forEach(c=>c.addEventListener('click',()=>{if(answered||picked.includes(+c.dataset.i))return;const ix=+c.dataset.i, expected=q.target[picked.length];if(ix!==expected){hadError=true;c.classList.remove('bad');void c.offsetWidth;c.classList.add('bad');wrongTap();return}picked.push(ix);tick();draw();if(picked.length===q.target.length){answered=true;const ok=currentMode==='exam'?!hadError:true;settle(ok,q.ex,`${q.title} → ${q.reading}`)}}));
 $('#resetOrder').addEventListener('click',()=>{if(answered)return;picked=[];hadError=currentMode==='exam'?hadError:false;draw()});$('#nextBtn').addEventListener('click',next);$('#menuBtn').addEventListener('click',returnMenu);draw();
}
function wrongTap(){streak=0;saveState();tone(false);vibrate([40,35,40]);showToast('そこじゃない！',false);$('#streakHud').textContent=`🔥 ${streak}`}
function settle(ok,ex,review){const p=pointsPer();if(ok){score+=p;streak++;maxStreak=Math.max(maxStreak,streak);tone(true);vibrate(35);showToast(streak>=5?`正解！ ${streak}連続🔥`:'正解！',true);if(streak%5===0)burst()}else{streak=0;tone(false);vibrate([45,30,45]);showToast('おしい！',false);mistakes.push(review)}saveState();renderHUD();const fb=$('#feedback');if(fb){fb.className='feedback show '+(ok?'ok':'ng');fb.innerHTML=`<b>${ok?'✅ 正解':'📝 復習ポイント'}</b><br>${esc(ex)}`}const nb=$('#nextBtn');if(nb)nb.disabled=false;if(currentMode==='exam'&&!ok)mistakes.push(review)}
function next(){qIndex++;if(qIndex>=deck.length){finish()}else renderQuestion()}
function finish(){$('#progressBar').style.width='100%';$('#questionArea').style.display='none';const total=deck.length*pointsPer();const pct=Math.round(score/total*100);const finalScore=currentMode==='exam'?score:pct;const medal=finalScore>=90?'🏆':finalScore>=75?'🥇':finalScore>=60?'🥈':'🥉';if(currentMode==='exam')recordBest(finalScore);if(finalScore>=80)burst(36);const unique=[...new Set(mistakes)].slice(0,8);$('#resultArea').innerHTML=`<div class="medal">${medal}</div><h2>${currentMode==='exam'?'定期テスト終了！':'ステージクリア！'}</h2><div class="bigScore">${finalScore}<small style="font-size:.38em">点</small></div><div class="resultStats"><span>正答相当 ${score}/${total}点</span><span>最大連続 ${maxStreak}</span><span>${finalScore>=80?'合格圏🔥':'もう1周で伸びる'}</span></div>${unique.length?`<h3>復習ポイント</h3><div class="reviewList">${unique.map(x=>`<div class="reviewItem"><b>CHECK</b> ${esc(x)}</div>`).join('')}</div>`:'<p class="sub">ミス記録なし。かなり仕上がってる。</p>'}<div class="actions" style="justify-content:center"><button class="btn primary" id="retryBtn">もう1周</button><button class="btn gold" id="examBtn">50問テスト</button><button class="btn ghost" id="resultMenu">メニュー</button></div>`;$('#resultArea').classList.add('show');$('#retryBtn').addEventListener('click',()=>startMode(currentMode));$('#examBtn').addEventListener('click',()=>startMode('exam'));$('#resultMenu').addEventListener('click',returnMenu)}

async function recordBest(v){v=Math.max(0,Math.min(100,Math.round(v)));const old=localStorage.getItem(BEST_KEY);if(old==null||v>Number(old))localStorage.setItem(BEST_KEY,String(v));updatePersistentUI();if(typeof window.__recordPeriodicTestScore==='function'){try{window.__recordPeriodicTestScore(v,{completed:true})}catch(e){console.warn(e)}}
 try{const c=window.GAKUSHU_FIREBASE_CONFIG;if(!c||!c.apiKey||!c.databaseURL)return;const [appMod,dbMod]=await Promise.all([import('https://www.gstatic.com/firebasejs/11.0.2/firebase-app.js'),import('https://www.gstatic.com/firebasejs/11.0.2/firebase-database.js')]);const app=appMod.getApps().length?appMod.getApps()[0]:appMod.initializeApp(c);const db=dbMod.getDatabase(app);const ref=dbMod.ref(db,`scoreUsers/${FIXED_USER}/subjects/${META.id}`);const snap=await dbMod.get(ref);const prev=snap.exists()?snap.val():{};await dbMod.set(ref,{...(prev||{}),best:Math.max(v,Number(prev?.best||0)),lastScore:v,subjectName:META.name,subjectId:META.id,scoreUserId:FIXED_USER,updatedAt:dbMod.serverTimestamp()})}catch(e){console.warn('score sync skipped',e)}}
function showToast(text,ok){const t=$('#toast');t.textContent=text;t.className='toast '+(ok?'':'bad');void t.offsetWidth;t.classList.add('show')}
function burst(n=22){const box=$('#confetti');box.innerHTML='';const colors=['#b91c1c','#f59e0b','#1d4ed8','#15803d','#7c3aed'];for(let i=0;i<n;i++){const el=document.createElement('i');el.style.left=Math.random()*100+'%';el.style.color=colors[i%colors.length];el.style.animationDelay=Math.random()*.22+'s';el.style.transform=`rotate(${Math.random()*360}deg)`;box.appendChild(el)}setTimeout(()=>box.innerHTML='',1500)}
function vibrate(v){if(navigator.vibrate)navigator.vibrate(v)}
function tone(ok){if(!soundOn)return;try{const AC=window.AudioContext||window.webkitAudioContext;if(!AC)return;const ac=new AC(),osc=ac.createOscillator(),gain=ac.createGain();osc.type='sine';osc.frequency.setValueAtTime(ok?660:190,ac.currentTime);if(ok)osc.frequency.exponentialRampToValueAtTime(880,ac.currentTime+.11);gain.gain.setValueAtTime(.055,ac.currentTime);gain.gain.exponentialRampToValueAtTime(.001,ac.currentTime+.18);osc.connect(gain);gain.connect(ac.destination);osc.start();osc.stop(ac.currentTime+.19)}catch{}}
function tick(){if(!soundOn)return;try{const AC=window.AudioContext||window.webkitAudioContext;if(!AC)return;const ac=new AC(),o=ac.createOscillator(),g=ac.createGain();o.frequency.value=460;g.gain.value=.025;o.connect(g);g.connect(ac.destination);o.start();g.gain.exponentialRampToValueAtTime(.001,ac.currentTime+.06);o.stop(ac.currentTime+.07)}catch{}}
updatePersistentUI();
if('serviceWorker' in navigator)window.addEventListener('load',()=>navigator.serviceWorker.register('./sw.js').catch(()=>{}));
})();
