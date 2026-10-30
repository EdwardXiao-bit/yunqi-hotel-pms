/* 云栖酒店 PMS —— 全局小脚本（T6 起按页面追加：二次确认、日期区间等） */
(function () {
  "use strict";

  // message 自动淡出（成功/提示类；错误类保留，等用户看完）
  document.querySelectorAll(".messages .alert-success, .messages .alert-info").forEach(function (el) {
    window.setTimeout(function () {
      if (window.jQuery && window.jQuery.fn.alert) {
        window.jQuery(el).fadeTo(400, 0, function () {
          window.jQuery(el).alert("close");
        });
      } else {
        el.style.display = "none";
      }
    }, 4000);
  });

  // 所有 form[method=post] 提交时禁用按钮，防重复提交（写操作统一走后端校验）
  document.querySelectorAll("form[method='post']").forEach(function (form) {
    form.addEventListener("submit", function () {
      var btn = form.querySelector("button[type='submit']");
      if (btn && !btn.dataset.keepEnabled) {
        window.setTimeout(function () {
          btn.disabled = true;
        }, 0);
      }
    });
  });
})();
