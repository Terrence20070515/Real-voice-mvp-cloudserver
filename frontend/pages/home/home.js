// pages/home/home.js
// 首页：店名 + 菜单 + AI 点单入口
// 店名与菜单全部由后端驱动 —— 店家后台换菜单后，进页面即变，前端零硬编码。
const api = require('../../api');
const util = require('../../utils/util');

Page({
  data: {
    shopName: '',        // 店名：后端 restaurant 优先，否则按菜单推断菜系，兜底「本店」
    shopMeta: '',        // 副标题：N 道菜 · M 个分类
    groups: [],          // 全部菜单（已分组）
    visibleGroups: [],   // 当前筛选后要渲染的
    cats: [],            // 分类 chips
    activeCat: '',       // '' = 全部
    loading: true,
    sessionId: ''
  },

  onLoad() {
    this.setData({ sessionId: util.getSessionId() });
    this.loadMenu();
  },

  onShow() {
    const sid = util.getSessionId();
    if (sid !== this.data.sessionId) {
      this.setData({ sessionId: sid });
    }
  },

  onPullDownRefresh() {
    this.loadMenu().then(() => wx.stopPullDownRefresh());
  },

  loadMenu() {
    this.setData({ loading: true });
    return api
      .getMenu()
      .then((raw) => {
        const menu = util.normalizeMenu(raw);
        const name = util.displayName(menu.restaurant, menu.groups);

        // 店名驱动导航栏标题：后台上传新菜单后，进页面即变
        wx.setNavigationBarTitle({ title: name });

        const hasMenu = menu.total > 0;
        this.setData({
          shopName: name,
          shopMeta: hasMenu
            ? menu.total + ' 道菜 · ' + menu.groups.length + ' 个分类'
            : '菜单尚未导入',
          groups: menu.groups,
          visibleGroups: menu.groups,
          cats: menu.groups.map((g) => ({ name: g.name, count: g.items.length })),
          activeCat: '',
          loading: false
        });
      })
      .catch((err) => {
        console.error('加载菜单失败', err);
        wx.setNavigationBarTitle({ title: '点餐' });
        this.setData({
          shopName: '本店',
          shopMeta: '菜单未加载',
          loading: false,
          groups: [],
          visibleGroups: [],
          cats: []
        });
        wx.showToast({ title: (err && err.message) || '加载菜单失败', icon: 'none' });
      });
  },

  // 分类筛选
  onSelectCat(e) {
    const cat = e.currentTarget.dataset.cat || '';
    const groups = this.data.groups;
    this.setData({
      activeCat: cat,
      visibleGroups: cat ? groups.filter((g) => g.name === cat) : groups
    });
  },

  goToChat() {
    wx.navigateTo({ url: '/pages/chat/chat' });
  },

  goToMenu() {
    wx.navigateTo({ url: '/pages/menu/menu' });
  },

  goToPay() {
    wx.navigateTo({ url: '/pages/pay/pay?session_id=' + this.data.sessionId });
  },

  showAbout() {
    wx.showModal({
      title: this.data.shopName || '本店',
      content: '本小程序由 AI 助手提供智能点餐服务，告诉它你想吃什么，剩下的交给它。',
      showCancel: false,
      confirmText: '知道了'
    });
  }
});
