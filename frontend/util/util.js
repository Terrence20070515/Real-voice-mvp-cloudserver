// utils/util.js — 通用工具函数

const util = {
  /**
   * 生成 session_id
   * 优先用 crypto.randomUUID()（高版本基础库支持），否则用时间戳+随机数
   * @returns {string} 形如 "sess_xxxxxxxx"
   */
  generateSessionId() {
    let uuid = '';
    try {
      if (typeof crypto !== 'undefined' && crypto.randomUUID) {
        uuid = crypto.randomUUID();
      }
    } catch (e) {
      uuid = '';
    }
    if (!uuid) {
      // 回退方案：时间戳 + 随机数
      const timestamp = Date.now().toString(36);
      const random = Math.random().toString(36).substring(2, 10);
      uuid = timestamp + '_' + random;
    }
    return 'sess_' + uuid;
  },

  /**
   * 获取持久化的 session_id
   * 如果 storage 里没有就生成一个新的并保存
   * @returns {string}
   */
  getSessionId() {
    let sid = '';
    try {
      sid = wx.getStorageSync('session_id');
    } catch (e) {
      sid = '';
    }
    if (!sid) {
      sid = this.generateSessionId();
      try {
        wx.setStorageSync('session_id', sid);
      } catch (e) {
        /* ignore */
      }
    }
    return sid;
  },

  /**
   * 清除持久化的 session_id（下次进入会生成新的）
   */
  clearSessionId() {
    try {
      wx.removeStorageSync('session_id');
    } catch (e) {
      /* ignore */
    }
  },

  /**
   * 保存 session_id 到 storage
   */
  saveSessionId(sid) {
    try {
      wx.setStorageSync('session_id', sid);
    } catch (e) {
      /* ignore */
    }
  },

  // ─── 聊天记录持久化（按 sessionId 存储）───
  /**
   * 保存聊天记录
   * @param {string} sessionId
   * @param {Array} messages
   */
  saveChatHistory(sessionId, messages) {
    if (!sessionId || !messages) return;
    try {
      // 限制最大保存 100 条，避免 storage 爆掉
      const toSave = messages.length > 100 ? messages.slice(-100) : messages;
      wx.setStorageSync('chat_history_' + sessionId, toSave);
    } catch (e) {
      /* storage 满了之类的，忽略 */
    }
  },

  /**
   * 加载聊天记录
   * @param {string} sessionId
   * @returns {Array}
   */
  loadChatHistory(sessionId) {
    if (!sessionId) return [];
    try {
      return wx.getStorageSync('chat_history_' + sessionId) || [];
    } catch (e) {
      return [];
    }
  },

  /**
   * 清除某个会话的聊天记录
   */
  clearChatHistory(sessionId) {
    if (!sessionId) return;
    try {
      wx.removeStorageSync('chat_history_' + sessionId);
    } catch (e) {
      /* ignore */
    }
  },

  /**
   * 格式化时间 HH:MM
   * @param {Date|number} date
   * @returns {string}
   */
  formatTime(date) {
    const d = date instanceof Date ? date : new Date(date || Date.now());
    const hours = String(d.getHours()).padStart(2, '0');
    const minutes = String(d.getMinutes()).padStart(2, '0');
    return hours + ':' + minutes;
  },

  /**
   * 判断字符串是否包含中文
   */
  hasChinese(str) {
    return /[\u4e00-\u9fa5]/.test(str || '');
  }
};

module.exports = util;
