// app.js
const config = require('./config');

App({
  onLaunch() {
    // 如果用云托管模式，初始化云开发
    if (config.useCloudContainer) {
      if (wx.cloud) {
        wx.cloud.init({
          env: config.cloudConfig.env,
          traceUser: true
        });
        console.log('云开发已初始化，环境:', config.cloudConfig.env);
      } else {
        console.error('当前基础库不支持云开发，请升级微信开发者工具');
      }
    }
  },

  // 全局数据
  globalData: {
    userInfo: null,
    sessionId: '',
    openid: ''
  }
});
