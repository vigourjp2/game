# 漢文ダンジョン v1.0.0 — Release Notes

## 追加
- `middle/japanese-kanbun/` を新規追加。
- TOPメニュー「中学」に `国語・漢文` カードを追加。
- 学習範囲：漢文入門①「返り点・送り仮名」。

## ゲームモード
1. 超速チュートリアル：返り点・送り仮名の基本を6カードで整理。
2. 返り点ハント：4択10問。
3. 読み順バトル：漢字を読む順にタップする操作型問題。
4. 送り仮名道場：4択10問。
5. 定期テスト決戦：50問、1問2点、100点満点。

## 実装品質
- スマートフォン 390px 幅で横スクロールなしを確認。
- 4択の回答→正誤表示→次問遷移を自動UIテスト。
- 読み順タップUI、やり直しUIを自動UIテスト。
- 50問テスト表示 `1 / 50` を確認。
- 添付写真の例題「勿・以・悪・小・為・之」を `悪→小→以→之→為→勿` で完走する自動UIテストを実施。
- JavaScript `node --check` PASS。
- 読み順問題の全target配列が全漢字を1回ずつ通る順列であることを検査。
- Firebase最高得点：既存TOPと同じ `middle-kanbun` ID / `gakushu-main` を使用。

## UX
- 正解/不正解の大きなフェード演出。
- 5連続正解ごとの紙吹雪。
- Web Audio効果音、端末対応時バイブ。
- 連続正解保存。
- PWA manifest / Service Worker を同梱。

## 配置
- `middle/japanese-kanbun/index.html`
- `middle/japanese-kanbun/styles.css`
- `middle/japanese-kanbun/app.js`
- `middle/japanese-kanbun/manifest.webmanifest`
- `middle/japanese-kanbun/sw.js`
- `middle/japanese-kanbun/icon-192.png`
- `middle/japanese-kanbun/icon-512.png`
