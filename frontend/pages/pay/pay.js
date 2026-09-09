// pages/pay/pay.js
const api = require('../../api');
const util = require('../../utils/util');

Page({
  data: {
    sessionId: '',
    orders: [],
    loading: true,
    payingOrderId: '',
    paySuccess: false
  },

  onLoad(options) {
    // 优先用 URL 参数里的 session_id，没有就用全局的
    let sid = options.session_id || util.getSessionId();
    this.setData({ sessionId: sid });
    this.loadOrders();
  },

  onShow() {
    // 每次显示都刷新一下订单
    if (this.data.sessionId) {
      this.loadOrders();
    }
  },

  loadOrders() {
    this.setData({ loading: true });
    api
      .getOrders(this.data.sessionId)
      .then((res) => {
        this.setData({
          orders: res.orders || [],
          loading: false
        });
      })
      .catch((err) => {
        console.error('查询订单失败', err);
        this.setData({ loading: false });
        wx.showToast({
          title: err.message || '查询订单失败',
          icon: 'none'
        });
      });
  },

  // 支付订单
  payOrder(e) {
    const orderId = e.currentTarget.dataset.id;
    if (!orderId || this.data.payingOrderId) return;

    this.setData({ payingOrderId: orderId });

    api
      .payOrder(orderId)
      .then((res) => {
        if (res.status === '已支付') {
          this.setData({ paySuccess: true });
          // 刷新订单列表
          setTimeout(() => {
            this.loadOrders();
            this.setData({ paySuccess: false });
          }, 2000);
        } else {
          wx.showToast({
            title: res.message || '支付失败',
            icon: 'none'
          });
        }
      })
      .catch((err) => {
        console.error('支付失败', err);
        wx.showToast({
          title: err.message || '支付失败',
          icon: 'none'
        });
      })
      .then(() => {
        this.setData({ payingOrderId: '' });
      });
  },

  // 返回聊天页
  backToChat() {
    wx.navigateBack();
  },

  // 继续点餐
  continueOrder() {
    wx.redirectTo({ url: '/pages/chat/chat' });
  },

  // 清台 / 换桌：顾客已离席，彻底重置（清账单 + 清 AI 记忆 + 换全新 session）
  clearTable() {
    const oldSid = this.data.sessionId;
    wx.showModal({
      title: '🧹 清台 / 换桌',
      content: '确认该桌顾客已离席？\n将清除账单与 AI 对话记忆，并为下一位顾客开启全新对话。',
      confirmText: '确认清台',
      confirmColor: '#d4232c',
      success: (res) => {
        if (!res.confirm) return;
        wx.showLoading({ title: '清台中...' });
        // 1) 后端清账单 + 清 AI 记忆（失败不影响本地重置）
        api
          .clearOrders(oldSid)
          .catch((err) => {
            console.warn('后端清台未成功（本地仍会重置）', err);
          })
          .then(() => {
            // 2) 换全新 session_id —— 下一轮对话绝对干净的根本保证
            const newSid = util.generateSessionId();
            util.saveSessionId(newSid);
            // 3) 清掉旧 session 的本地聊天记录
            util.clearChatHistory(oldSid);
            wx.hideLoading();
            wx.showToast({ title: '清台完成，已为新客准备', icon: 'success' });
            // 4) 重定向回聊天页，让新 session 立即生效（下一顾客面对干净对话）
            setTimeout(() => {
              wx.redirectTo({ url: '/pages/chat/chat' });
            }, 800);
          });
      }
    });
  }
});
