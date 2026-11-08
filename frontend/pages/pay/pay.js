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
});
