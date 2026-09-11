// config.js — 全局配置
//
// ⚠️ 修改 API 地址只改这一个文件即可，不要在每个页面里硬编码 URL
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
  timeout: 30000,

  // ─── 餐厅信息 ───
  restaurant: {
    name: '川味小馆',
    slogan: 'AI 智能点餐 · 美味无需等待',
    hours: '11:00 - 22:00',
    address: '成都市锦江区春熙路 88 号',
    phone: '028-88888888'
  }
};

module.exports = config;
