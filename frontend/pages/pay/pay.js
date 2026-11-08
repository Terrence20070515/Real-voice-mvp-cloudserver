// pages/pay/pay.js
const api = require('../../api');
const util = require('../../utils/util');
const i18n = require('../../utils/i18n');

Page({
  data: {
    sessionId: '',
    orders: [],
    loading: true,
    payingOrderId: '',
    paySuccess: false,
    lang: i18n.current(),
    i18n: i18n.pack(i18n.current())
  },

  onLoad(options) {
    // 优先用 URL 参数里的 session_id，没有就用全局的
    let sid = options.session_id || util.getSessionId();
    const lang = i18n.current();
    this.setData({ sessionId: sid, lang: lang, i18n: i18n.pack(lang) });
    this.loadOrders();
  },

  onShow() {
    // 每次显示都刷新一下订单，顺便跟上语言变化
    const lang = i18n.current();
    if (lang !== this.data.lang) {
      this.setData({ lang: lang, i18n: i18n.pack(lang) });
    }
    if (this.data.sessionId) {
      this.loadOrders();
    }
  },

  /** 语言开关 */
  toggleLang() {
    const lang = i18n.toggle();
    this.setData({ lang: lang, i18n: i18n.pack(lang) });
  },

  loadOrders() {
    this.setData({ loading: true });
    const lang = this.data.lang;
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
          title: err.message || i18n.pack(lang).queryOrdersFail,
          icon: 'none'
        });
      });
  },

  // 支付订单
  payOrder(e) {
    const orderId = e.currentTarget.dataset.id;
    if (!orderId || this.data.payingOrderId) return;

    this.setData({ payingOrderId: orderId });
    const t = this.data.i18n;

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
            title: res.message || t.payFail,
            icon: 'none'
          });
        }
      })
      .catch((err) => {
        console.error('支付失败', err);
        wx.showToast({
          title: err.message || t.payFail,
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
