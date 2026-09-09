// pages/home/home.js
const api = require('../../api');
const util = require('../../utils/util');
const config = require('../../config');

Page({
  data: {
    menuData: [],
    signatureDishes: [],
    loading: true,
    restaurantName: config.restaurant.name,
    slogan: config.restaurant.slogan,
    hours: config.restaurant.hours,
    address: config.restaurant.address,
    phone: config.restaurant.phone,
    sessionId: ''
  },

  onLoad() {
    // 进入时获取 session_id
    const sid = util.getSessionId();
    this.setData({ sessionId: sid });

    // 加载菜单
    this.loadMenuData();
  },

  onShow() {
    // 每次显示都重新拿一次 sessionId（清空对话后可能变了）
    const sid = util.getSessionId();
    if (sid !== this.data.sessionId) {
      this.setData({ sessionId: sid });
    }
  },

  onPullDownRefresh() {
    this.loadMenuData().then(() => {
      wx.stopPullDownRefresh();
    });
  },

  loadMenuData() {
    this.setData({ loading: true });
    return api
      .getMenu()
      .then((data) => {
        const grouped = this.groupByCategory(data);
        // 提取招牌必点的菜作为推荐
        const signature = (grouped.find((g) => g.name === '招牌必点') || { items: [] }).items.slice(0, 5);
        this.setData({
          menuData: grouped,
          signatureDishes: signature,
          loading: false
        });
      })
      .catch((err) => {
        console.error('加载菜单失败', err);
        this.setData({ loading: false });
        wx.showToast({
          title: err.message || '加载菜单失败',
          icon: 'none'
        });
      });
  },

  groupByCategory(items) {
    if (!Array.isArray(items)) return [];
    const map = {};
    const order = ['招牌必点', '凉菜', '热菜·川味', '热菜·清淡', '汤类', '主食', '饮品'];
    items.forEach((item) => {
      const cat = item['分类'] || '其他';
      if (!map[cat]) map[cat] = { name: cat, items: [] };
      map[cat].items.push({
        name: item['菜品'],
        price: item['价格'],
        spicy: item['辣度'],
        description: item['描述'],
        allergens: item['过敏原']
      });
    });
    const result = order.filter((n) => map[n]).map((n) => map[n]);
    Object.keys(map).forEach((n) => {
      if (order.indexOf(n) === -1) result.push(map[n]);
    });
    return result;
  },

  // 跳转到 AI 点单
  goToChat() {
    wx.navigateTo({ url: '/pages/chat/chat' });
  },

  // 跳转到完整菜单
  goToMenu() {
    wx.navigateTo({ url: '/pages/menu/menu' });
  },

  // 跳转到买单页
  goToPay() {
    wx.navigateTo({
      url: '/pages/pay/pay?session_id=' + this.data.sessionId
    });
  },

  // 拨打电话
  callRestaurant() {
    wx.makePhoneCall({
      phoneNumber: this.data.phone,
      fail: () => {
        wx.showToast({ title: '取消拨打', icon: 'none' });
      }
    });
  },

  // 关于我们
  showAbout() {
    wx.showModal({
      title: this.data.restaurantName,
      content: '川味小馆成立于2010年，专注正宗川菜，传承百年老味道。\n\n本小程序由 AI 助手提供智能点餐服务，告诉它你想吃什么，剩下的交给它。',
      showCancel: false,
      confirmText: '知道了'
    });
  }
});
