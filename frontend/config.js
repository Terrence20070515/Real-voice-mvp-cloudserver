// config.js — 全局配置
//
// ⚠️ 修改 API 地址只改这一个文件即可，不要在每个页面里硬编码 URL

const config = {
  // ─── 后端调用模式 ───
  // false: 传统 wx.request 调用（开发期 + 内网穿透 + 自建服务器都用这个）
  // true:  微云托管 wx.cloud.callContainer 调用（部署到微信云托管后用）
  useCloudContainer: false,

  // ─── 模式 1：传统 wx.request 配置 ───
  // 三种场景：
  // 1️⃣ 开发者工具调试：'http://localhost:8001'
  // 2️⃣ 真机调试（手机电脑同 WiFi）：'http://192.168.1.26:8001'
  // 3️⃣ 自建服务器（已配 HTTPS）：'https://api.yourdomain.com'
  apiBaseUrl: 'http://YOUR_SERVER_IP:8080',

  // ─── 模式 2：微信云托管配置 ───
  // 部署到云托管后，从「云开发 → 云托管 → 服务列表」里拿这些信息
  cloudConfig: {
    env: 'cloud1-d4gmpeyjv74553c95',         // 云开发环境 ID
    serviceName: 'real-voice-mvp',             // 云托管服务名
    path: '/'                                  // 路径前缀，一般用 '/'
  },

  // ─── 云托管公网地址（用于耗时接口如 AI 对话）───
  // callContainer 有 15 秒硬限制，AI 对话可能需要 30+ 秒
  // 在「云托管 → 服务详情 → 公网访问」里找到这个地址
  // 格式：https://xxx.ap-shanghai.app.tcloudbase.com 或自定义域名
  cloudPublicUrl: 'https://real-voice-mvp-279101-7-1449503768.sh.run.tcloudbase.com',   // ← 填上你的公网地址，留空则 chat 也走 callContainer（会超时）

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
