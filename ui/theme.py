"""Cohesive local UI. No remote font or image services required."""
from nicegui import ui
CSS = r"""
:root {--ink:#172c43;--muted:#748396;--page:#f5f7fa;--surface:#fff;--line:#e4eaf0;--brand:#087f8c;--soft:#edf7f7;--nav:#10283f;}
body {font-family:'Segoe UI',Inter,system-ui,sans-serif;background:var(--page);color:var(--ink);font-size:14px;}
body.body--dark {--ink:#e1eaf3;--muted:#99adbf;--page:#101c2a;--surface:#18293b;--line:#2b4054;--soft:#163d44;--nav:#0c1927;}
* {box-sizing:border-box;} .nicegui-content {padding:0;gap:0;} .q-page {background:var(--page);}
.q-card {background:var(--surface);color:var(--ink);box-shadow:none;}
.q-field {font-family:inherit;} .q-btn {text-transform:none;font-weight:600;letter-spacing:0;box-shadow:none;border-radius:9px;}
.q-btn--rectangle {border-radius:9px;} .q-field--outlined .q-field__control {border-radius:9px;}
.q-field--outlined .q-field__control:before {border-color:var(--line);}
.q-table__container {background:var(--surface);color:var(--ink);box-shadow:none;border:1px solid var(--line);}
.app-sidebar {background:var(--nav)!important;color:#c4d2df;border-right:0!important;padding:28px 17px;}
.brand {font-weight:750;font-size:25px;letter-spacing:-1px;color:#fff;}
.brand-small {font-size:11px;color:#9ab6c7;letter-spacing:.2px;font-weight:400;}
.nav-label {color:#7d9ab0;font-size:10px;letter-spacing:1.7px;font-weight:650;margin:24px 12px 9px;}
.nav-link {width:100%;display:flex;align-items:center;gap:11px;color:#b7cadb;text-decoration:none;padding:11px 13px;border-radius:9px;font-size:13px;margin:2px 0;transition:background .15s;}
.nav-link:hover {background:#ffffff09;color:#fff;}.nav-active {background:#1e4758!important;color:#a7eee4!important;border:1px solid #39727a66;}
.app-sidebar .q-btn {color:#8ed5cf!important;} body.body--dark .text-primary {color:#78d4cb!important;}
.topbar {background:var(--surface)!important;color:var(--ink);height:76px;border-bottom:1px solid var(--line);box-shadow:none;}
.page-wrap {max-width:1580px;padding:30px 38px 40px;width:100%;margin:0 auto;animation:arrive .2s ease-out;}
@keyframes arrive {from {opacity:.6;transform:translateY(4px)} to {opacity:1;transform:translateY(0)}}
.eyebrow {font-size:10px;letter-spacing:1.8px;font-weight:700;text-transform:uppercase;color:var(--brand);}
.page-title {font-size:29px;font-weight:700;letter-spacing:-1px;line-height:1.25;color:var(--ink);}
.subtle {color:var(--muted);line-height:1.6;font-size:13px;}
.panel {border:1px solid var(--line);border-radius:13px;background:var(--surface);padding:23px;}
.panel-title {font-weight:650;font-size:16px;letter-spacing:-.2px;}
.welcome {background:linear-gradient(115deg,#142f4b,#173f51);color:white;border:1px solid #224d61;border-radius:17px;padding:34px 36px;position:relative;overflow:hidden;}
.welcome:after {content:'';position:absolute;width:260px;height:260px;border:1px solid #ffffff12;border-radius:50%;right:-50px;top:-100px;box-shadow:0 0 0 42px #ffffff04,0 0 0 84px #ffffff04;pointer-events:none;}
.hero-title {font-size:33px;font-weight:650;letter-spacing:-1.2px;line-height:1.25;max-width:650px;}
.hero-copy {color:#aac6d3;font-size:14px;line-height:1.8;max-width:560px;}
.stat-number {font-size:29px;line-height:1.2;font-weight:650;letter-spacing:-.8px;}
.icon-tile {width:42px;height:42px;border-radius:11px;background:var(--soft);color:var(--brand);display:flex;align-items:center;justify-content:center;}
.workspace-card {transition:box-shadow .15s,border-color .15s;}.workspace-card:hover {border-color:#72b7bc;box-shadow:0 4px 18px #10283f08;}
.doc-grid {display:grid;grid-template-columns:repeat(auto-fill,minmax(260px,1fr));gap:17px;width:100%;}
.doc-icon {background:#f0f4fa;border:1px solid #e4eaf0;color:#4c6c90;width:46px;height:55px;border-radius:7px;display:flex;align-items:center;justify-content:center;}
.dropzone {border:1.5px dashed #93bfc7!important;border-radius:13px!important;background:var(--soft)!important;box-shadow:none!important;min-height:155px;width:100%!important;}
.dropzone .q-uploader__header {background:transparent!important;color:var(--brand)!important;}.dropzone .q-uploader__list {background:var(--surface);min-height:70px;}
.empty-state {padding:35px 24px;text-align:center;align-items:center;justify-content:center;gap:12px;border:1px dashed var(--line);border-radius:12px;width:100%;background:var(--surface);}
.research-grid {display:grid;grid-template-columns:220px minmax(320px,1fr) minmax(300px,37%);gap:16px;align-items:start;}
.research-grid.source-collapsed {grid-template-columns:0 minmax(340px,1fr) minmax(300px,40%);}.research-grid.source-collapsed>.source-panel {display:none;}
.source-panel {position:sticky;top:96px;max-height:calc(100vh - 125px);overflow:auto;}
.research-main {min-width:0;}.evidence-panel {position:sticky;top:96px;min-width:0;max-height:calc(100vh - 116px);overflow:auto;}
.source-item {padding:11px 0;border-bottom:1px solid var(--line);}
.question-bubble {background:var(--soft);border:1px solid #9ecbcb55;border-radius:12px 12px 3px 12px;padding:17px 20px;margin-left:35px;}
.answer-card {background:var(--surface);border:1px solid var(--line);border-radius:13px;padding:22px;}
.citation-chip {font-size:11px!important;border-radius:6px!important;padding:2px 7px!important;min-height:25px!important;max-width:100%;}
.quote {border-left:3px solid #55b7ad;background:var(--soft);padding:12px 15px;font-size:12px;line-height:1.8;border-radius:0 7px 7px 0;white-space:pre-wrap;overflow-wrap:anywhere;}
.source-preview {background:#dce3ea;border:1px solid var(--line);border-radius:7px;overflow:auto;max-height:560px;}
.source-preview img {display:block;max-width:100%;height:auto;}
.brief-editor {font-family:Georgia,serif;font-size:16px;line-height:1.8;background:var(--surface);min-height:600px;}
.fineprint {font-size:11px;color:var(--muted);line-height:1.6;}.q-dialog__inner>div {max-width:min(92vw,1000px)!important;}
.graph-card {min-width:0;overflow:hidden;}.q-markdown {overflow-wrap:anywhere;}.q-markdown h1 {font-size:28px;}.q-markdown h2 {font-size:21px;}.q-markdown h3 {font-size:17px;}
.two-columns {display:grid;grid-template-columns:minmax(0,1.4fr) minmax(0,1fr);gap:22px;width:100%;}
.q-select .q-field__control-container,.q-select .q-field__native {min-width:0;}
.q-select .q-field__native>span {max-width:100%;overflow-wrap:anywhere;white-space:normal;word-break:break-word;}
.q-table td {white-space:normal!important;max-width:600px;overflow-wrap:anywhere;}
.brief-editor .q-editor__content {padding:25px 30px;min-height:500px;max-height:750px;overflow:auto;}
.brief-editor h1 {font-size:29px;line-height:1.3;margin:0 0 22px;letter-spacing:-.5px;}
.brief-editor h2 {font-size:23px;line-height:1.4;margin:28px 0 12px;letter-spacing:-.3px;}
.brief-editor h3 {font-size:19px;line-height:1.4;margin:22px 0 10px;letter-spacing:0;}
.brief-editor p {margin:0 0 14px;}.brief-layout {display:grid;grid-template-columns:minmax(0,.85fr) minmax(0,1.2fr);gap:22px;width:100%;}
body.body--dark .nicegui-echart svg text {fill:#bad0e0!important;}
@media(max-width:1180px) {.brief-layout{grid-template-columns:1fr}}
@media (max-width:1180px) {.page-wrap{padding:25px 24px}.research-grid{grid-template-columns:180px minmax(0,1fr)}.evidence-panel{grid-column:1/-1;position:static;max-height:none}.research-grid.source-collapsed{grid-template-columns:minmax(0,1fr)}.two-columns{grid-template-columns:1fr}}
@media (max-width:760px) {.page-wrap{padding:20px 15px}.welcome{padding:25px}.hero-title{font-size:28px}.page-title{font-size:25px}.research-grid{grid-template-columns:1fr}.source-panel{position:static;max-height:200px}.topbar{height:66px}.global-search{display:none!important}.panel{padding:17px}}
/* Everyday interface: three destinations, generous reading space, quiet controls. */
.page-wrap {max-width:1440px;padding-top:32px;}
.app-sidebar {padding-top:32px;}.nav-link {padding:14px 13px;font-size:14px;}
.home-hero {padding:42px 42px 30px;background:linear-gradient(120deg,#102c46,#164455);border-radius:22px;position:relative;overflow:hidden;}
.home-hero:after {content:'';position:absolute;right:-80px;top:-150px;width:400px;height:400px;border:1px solid #a6f3df16;border-radius:50%;box-shadow:0 0 0 55px #9beedb05,0 0 0 110px #9beedb04;pointer-events:none;}
.hero-kicker {color:#a2e1d7;font-size:12px;font-weight:550;letter-spacing:.3px;}
.home-title {font-size:clamp(34px,4vw,52px);line-height:1.12;font-weight:650;letter-spacing:-2px;color:#fff;}
.home-copy {font-size:15px;line-height:1.8;color:#bed0dc;max-width:650px;}
.home-question {background:var(--surface);border:1px solid #ffffff22;border-radius:13px;padding:8px 9px 8px 18px;z-index:1;margin-top:9px;box-shadow:0 6px 24px #00152322;}
.home-question input {font-size:16px;color:var(--ink);}.home-question .q-btn {min-height:44px;padding:0 18px;}
.example-questions {z-index:1;color:#b7cfdb;align-items:baseline;}.example-question {color:#d9e9ef!important;text-align:left;font-weight:400;font-size:11px!important;border:1px solid #ffffff1c;padding:4px 8px!important;}
.home-bottom {display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1.05fr);gap:26px;align-items:start;}
.upload-panel {padding:25px;border-radius:16px;}.simple-upload {margin-top:9px;min-height:195px;border-radius:12px!important;}
.simple-upload .q-uploader__header {min-height:190px;padding:25px 18px;}.simple-upload .q-uploader__title {font-size:14px;white-space:normal;line-height:1.7;}
.simple-upload .q-uploader__list {display:none;}
.simple-upload .q-uploader__subtitle {display:none;}
.example-question .q-btn__content {color:#d9e9ef!important;}
.home-empty {padding:45px 24px;background:var(--surface);border:1px solid var(--line);border-radius:16px;}
.document-row {padding:19px 20px;border:1px solid var(--line);border-radius:13px;background:var(--surface);}
.document-row:hover {border-color:#92c4c7;}.job-row {border-top:1px solid var(--line);padding:12px 0 2px;}
.simple-research {display:grid;grid-template-columns:minmax(0,1.35fr) minmax(300px,.85fr);gap:22px;align-items:start;}
.simple-evidence {position:sticky;top:94px;max-height:calc(100vh - 112px);overflow:auto;scroll-margin-top:95px;}
.simple-source-choice {background:var(--surface);border:1px solid var(--line);border-radius:12px;}.simple-source-choice .q-expansion-item__content {padding:0 15px 16px;}
.answer-card {padding:25px;border-radius:16px;}.answer-card .text-sm {font-size:15px;line-height:1.9;}
.citation-chip {white-space:normal;overflow-wrap:anywhere;text-align:left;background:var(--soft);color:var(--brand);line-height:1.6;}
.question-composer {border-color:#99c3c8;border-radius:16px;}.research-tabs {border-bottom:1px solid var(--line);}.q-tab-panel {padding:0;}
@media(max-width:1180px) {.simple-research{grid-template-columns:minmax(0,1fr) minmax(280px,.85fr)}.home-hero{padding:32px;}.home-bottom{gap:20px;}}
@media(max-width:800px) {.home-bottom,.simple-research{grid-template-columns:1fr}.simple-evidence{position:static;max-height:none}.home-title{font-size:40px}.home-hero{padding:28px;}.example-question{max-width:100%;}.home-question{padding:8px 10px;}.home-question .q-btn{padding:0 12px}}
@media(max-width:480px) {.home-hero{padding:25px 20px;}.home-title{font-size:36px;letter-spacing:-1.5px;}.home-copy{font-size:13px;}.home-question{flex-wrap:wrap;gap:3px}.home-question>.q-field{flex-basis:100%;}.home-question>.q-btn{width:100%;}.example-questions{gap:7px}.answer-card{padding:18px}.research-tabs .q-tab{padding:0 8px;min-width:0}.research-tabs .q-tab__label{font-size:12px}}
"""
def install_theme():
    ui.colors(primary="#087f8c", secondary="#173f51", accent="#23a69b", positive="#16896a", warning="#ba801c", negative="#bd4c54")
    ui.add_css(CSS)
