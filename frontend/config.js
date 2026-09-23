// config.js — 全局配置
//
// 修改 API 地址只改这一个文件即可，不要在每个页面里硬编码 URL
//
// 只保留两种开发模式：
//   1. 云服务器（已部署：腾讯云 Docker，后端端口 8080）
//   2. 本地开发（微信开发者工具调试，后端本地跑）

// ─── 模式开关 ───
// true  = 云服务器（apiBaseUrl 指向云服务器）
// false = 本地开发（apiBaseUrl 指向 localhost）
const USE_CLOUD_SERVER = true;

const config = {
  // ─── 后端地址 ───
  apiBaseUrl: USE_CLOUD_SERVER
    ? 'http://101.34.242.247:8080'
    : 'http://localhost:8001',

  // ─── 请求超时时间（毫秒）───
  timeout: 30000
};

// 这里**不再保存任何门店信息**（店名 / 营业时间 / 地址 / 电话）。
//
// 店名完全由后端菜单驱动，规则见 utils/util.js 的 displayName()：
//   1. 后端 /api/menu 返回了 restaurant → 直接用它
//   2. 没返回 → 按菜单内容推断菜系（川菜 / 日料 / 粤菜 …）
//   3. 都推不出 → 显示「本店」
//
// 因此店家后台换个菜单，小程序进页面就会跟着变，不需要改这里、也不需要重新发版。

module.exports = config;
