// pages/home/home.js
// 首页：店名 + 菜单 + AI 点单入口
// 店名与菜单全部由后端驱动 —— 店家后台换菜单后，进页面即变，前端零硬编码。
const api = require('../../api');
const util = require('../../utils/util');
const i18n = require('../../utils/i18n');

Page({
  data: {
    shopName: '',        // 店名：后端 restaurant 优先，否则按菜单推断菜系，兜底「本店」
    shopMeta: '',        // 副标题：N 道菜 · M 个分类（按当前语言拼装）
    total: 0,            // 菜品总数（用于切换语言后重算副标题）
    catCount: 0,         // 分类数
    groups: [],          // 全部菜单（已分组）
    visibleGroups: [],   // 当前筛选后要渲染的
    cats: [],            // 分类 chips
    activeCat: '',       // '' = 全部
    loading: true,
    sessionId: '',
    lang: i18n.current(),
    i18n: i18n.pack(i18n.current())
  },

  onLoad() {
    const lang = i18n.current();
    this.setData({
      sessionId: util.getSessionId(),
      lang: lang,
      i18n: i18n.pack(lang)
    });
    this.loadMenu();
  },

  onShow() {
    const sid = util.getSessionId();
    const lang = i18n.current();
    const patch = {};
    if (sid !== this.data.sessionId) patch.sessionId = sid;
    // 从其它页面切了语言，回来要跟上（含菜品辣度、描述显隐）
    if (lang !== this.data.lang) {
      patch.lang = lang;
      patch.i18n = i18n.pack(lang);
      if (this.data.groups.length) {
        patch.groups = this.decorateGroups(this.data.groups, lang);
        patch.visibleGroups = this.data.activeCat
          ? patch.groups.filter((g) => g.name === this.data.activeCat)
          : patch.groups;
      }
      patch.shopMeta = this.metaText(this.data.total, this.data.catCount, lang);
    }
    if (Object.keys(patch).length) {
      this.setData(patch);
    }
  },

  /** 副标题：N 道菜 · M 个分类 */
  metaText(total, catCount, lang) {
    const t = i18n.pack(lang || this.data.lang);
    if (!total) return t.menuNotImported;
    return total + ' ' + t.dishUnit + ' · ' + catCount + ' ' + t.catUnit;
  },

  /** 首页语言开关 */
  toggleLang() {
    const lang = i18n.toggle();
    this.setData({
      lang: lang,
      i18n: i18n.pack(lang),
      shopMeta: this.metaText(this.data.total, this.data.catCount, lang),
      // 英文下隐藏中文菜品描述
      groups: this.decorateGroups(this.data.groups, lang),
      visibleGroups: this.decorateGroups(
        this.data.activeCat
          ? this.data.groups.filter((g) => g.name === this.data.activeCat)
          : this.data.groups,
        lang
      )
    });
  },

  /** 给菜品补上语言相关字段：辣度翻译、是否显示描述 */
  decorateGroups(groups, lang) {
    return groups.map((g) => ({
      name: g.name,
      items: g.items.map((d) =>
        Object.assign({}, d, {
          spicyText: i18n.spicyText(d.spicy, lang),
          showSpicy: !!d.spicy && d.spicy !== '不辣',
          showDesc: lang !== 'en' && !!d.desc
        })
      )
    }));
  },

  onPullDownRefresh() {
    this.loadMenu().then(() => wx.stopPullDownRefresh());
  },

  loadMenu() {
    this.setData({ loading: true });
    const lang = this.data.lang;
    return api
      .getMenu()
      .then((raw) => {
        const menu = util.normalizeMenu(raw);
        const name = util.displayName(menu.restaurant, menu.groups);
        const groups = this.decorateGroups(menu.groups, lang);

        // 店名驱动导航栏标题：后台上传新菜单后，进页面即变
        wx.setNavigationBarTitle({ title: name });

        this.setData({
          shopName: name,
          shopMeta: this.metaText(menu.total, menu.groups.length, lang),
          total: menu.total,
          catCount: menu.groups.length,
          groups: groups,
          visibleGroups: groups,
          cats: menu.groups.map((g) => ({ name: g.name, count: g.items.length })),
          activeCat: '',
          loading: false
        });
      })
      .catch((err) => {
        console.error('加载菜单失败', err);
        wx.setNavigationBarTitle({ title: i18n.pack(lang).assistantTitle });
        this.setData({
          shopName: i18n.pack(lang).defaultShop,
          shopMeta: i18n.pack(lang).menuNotLoaded,
          total: 0,
          catCount: 0,
          loading: false,
          groups: [],
          visibleGroups: [],
          cats: []
        });
        wx.showToast({ title: (err && err.message) || i18n.pack(lang).loadMenuFail, icon: 'none' });
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
    const t = this.data.i18n;
    wx.showModal({
      title: this.data.shopName || t.defaultShop,
      content: t.aboutBody,
      showCancel: false,
      confirmText: t.aboutConfirm
    });
  }
});
