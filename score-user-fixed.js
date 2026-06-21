/* 学習サイト Firebase最高点：入力なし・全端末共通ID版 */
window.GAKUSHU_FIXED_SCORE_USER = "gakushu-main";
window.GAKUSHU_SCORE_NO_INPUT = true;
(function(){
  try {
    localStorage.setItem("gakushuScoreUser", "gakushu-main");
    localStorage.setItem("scoreUserId", "gakushu-main");
    localStorage.setItem("shareId", "gakushu-main");
  } catch(e) {}
})();
