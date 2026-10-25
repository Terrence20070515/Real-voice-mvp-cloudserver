// api.js — 统一 API 调用模块
//
// 支持两种模式（config.js 里切换）：
// 1. 传统 wx.request：开发期、内网穿透、自建服务器
// 2. wx.cloud.callContainer：微信云托管（自动 HTTPS + 鉴权）

const config = require('./config');

/**
 * 统一的请求方法
 * 根据 config.useCloudContainer 选择调用方式
 */
function request(options) {
  if (config.useCloudContainer) {
    return requestViaCloudContainer(options);
  }
  return requestViaWx(options);
}

// ─── 模式 1：传统 wx.request ───
// 支持 options.baseUrl 覆盖默认 apiBaseUrl（chat 走公网时用）
function requestViaWx(options) {
  var baseUrl = options.baseUrl || config.apiBaseUrl;
  return new Promise((resolve, reject) => {
    wx.request({
      url: baseUrl + options.url,
      method: options.method || 'GET',
      data: options.data,
      header: Object.assign(
        { 'Content-Type': 'application/json' },
        options.header || {}
      ),
      timeout: options.timeout || config.timeout,
      success: (res) => {
        if (res.statusCode >= 200 && res.statusCode < 300) {
          resolve(res.data);
        } else {
          const detail =
            (res.data && (res.data.detail || res.data.message)) ||
            '请求失败 (' + res.statusCode + ')';
          reject({ statusCode: res.statusCode, message: detail, data: res.data });
        }
      },
      fail: (err) => {
        let message = '网络连接失败';
        if (err.errMsg && err.errMsg.indexOf('timeout') >= 0) {
          message = '请求超时，请稍后再试';
        } else if (err.errMsg && err.errMsg.indexOf('url not in domain list') >= 0) {
          message = '请在微信开发者工具勾选「不校验合法域名」';
        } else if (err.errMsg && err.errMsg.indexOf('fail') >= 0) {
          message = '无法连接后端服务，请确认后端已启动';
        }
        reject({ message: message, raw: err });
      }
    });
  });
}

// ─── 模式 2：wx.cloud.callContainer（微信云托管）───
// 官方文档：https://developers.weixin.qq.com/miniprogram/dev/wxcloudservice/wxcloudrun/src/development/call/mini.html
// 关键点：
//   1. config 里只有 env，没有 service
//   2. 服务名通过 header 的 X-WX-SERVICE 传递
//   3. path 以 / 开头，对应后端路由路径
function requestViaCloudContainer(options) {
  return new Promise((resolve, reject) => {
    wx.cloud.callContainer({
      config: {
        env: config.cloudConfig.env
      },
      path: options.url.startsWith('/') ? options.url : '/' + options.url,
      method: options.method || 'GET',
      header: Object.assign(
        {
          'Content-Type': 'application/json',
          'X-WX-SERVICE': config.cloudConfig.serviceName  // 服务名必须在 header 里！
        },
        options.header || {}
      ),
      data: options.data,
      timeout: Math.min(options.timeout || config.timeout, 15000), // 云托管最大 15 秒
      success: (res) => {
        if (res.statusCode >= 200 && res.statusCode < 300) {
          resolve(res.data);
        } else {
          const detail =
            (res.data && (res.data.detail || res.data.message)) ||
            '请求失败 (' + res.statusCode + ')';
          reject({ statusCode: res.statusCode, message: detail, data: res.data });
        }
      },
      fail: (err) => {
        const errMsg = (err && err.errMsg) || JSON.stringify(err);
        console.error('[云托管失败]', 'env=' + config.cloudConfig.env, 'service=' + config.cloudConfig.serviceName, 'path=' + (options.url.startsWith('/') ? options.url : '/' + options.url), 'error=', errMsg);
        reject({
          message: '云托管调用失败：' + errMsg,
          raw: err
        });
      }
    });
  });
}

const api = {
  /**
   * 查询菜单
   */
  getMenu(params) {
    params = params || {};
    const query = [];
    if (params.category) query.push('category=' + encodeURIComponent(params.category));
    if (params.keyword) query.push('keyword=' + encodeURIComponent(params.keyword));
    const url = '/api/menu' + (query.length ? '?' + query.join('&') : '');
    return request({ url: url, method: 'GET' });
  },

  /**
   * 语音转文字：上传录音文件到 /api/asr，返回 Promise<{text}>
   */
  asrUpload(filePath) {
    var baseUrl = config.apiBaseUrl;
    return new Promise((resolve, reject) => {
      wx.uploadFile({
        url: baseUrl + '/api/asr',
        filePath: filePath,
        name: 'file',
        success: (res) => {
          try {
            var d = JSON.parse(res.data);
            if (res.statusCode === 200) {
              resolve(d);
            } else {
              reject(new Error(d.detail || '语音识别失败'));
            }
          } catch (e) {
            reject(new Error('语音识别响应异常'));
          }
        },
        fail: (e) => reject(new Error((e && e.errMsg) || '录音上传失败')),
      });
    });
  },

  /**
   * AI 对话（走公网 HTTP，不受 callContainer 15 秒限制）
   * 当配置了 cloudPublicUrl 时自动使用公网地址
   */
  chat(params) {
    // 如果配了公网地址，chat 走 wx.request（60秒超时）
    if (config.useCloudContainer && config.cloudPublicUrl) {
      return requestViaWx({
        url: '/api/chat',
        method: 'POST',
        data: { session_id: params.sessionId, message: params.message },
        timeout: 60000,  // AI 对话给足时间
        baseUrl: config.cloudPublicUrl  // 走云托管公网地址
      }).then(function (data) {
        return data.reply;
      });
    }
    // 没配公网地址，回退到默认通道
    return request({
      url: '/api/chat',
      method: 'POST',
      data: { session_id: params.sessionId, message: params.message }
    }).then(function (data) {
      return data.reply;
    });
  },

  /**
   * 清除会话历史
   */
  clearSession(sessionId) {
    return request({
      url: '/api/session/clear?session_id=' + encodeURIComponent(sessionId),
      method: 'POST'
    });
  },

  /**
   * 微信登录
   */
  login(code) {
    return request({
      url: '/api/login',
      method: 'POST',
      data: { code: code }
    });
  },

  /**
   * 查询某 session 的所有订单
   */
  getOrders(sessionId) {
    return request({
      url: '/api/orders/' + encodeURIComponent(sessionId),
      method: 'GET'
    });
  },

  /**
   * 支付订单（模拟）
   */
  payOrder(orderId) {
    return request({
      url: '/api/orders/' + encodeURIComponent(orderId) + '/pay',
      method: 'POST'
    });
  },

  /**
   * 清台：清除某 session 的所有订单 + 对话历史
   */
  clearOrders(sessionId) {
    return request({
      url: '/api/orders/clear?session_id=' + encodeURIComponent(sessionId),
      method: 'POST'
    });
  }
};

module.exports = api;
