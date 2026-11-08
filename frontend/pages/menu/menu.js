// pages/menu/menu.js
const api = require('../../api');
const i18n = require('../../utils/i18n');

Page({
  data: {
    categories: [],
    activeCategory: '',
    loading: true,
    error: '',
    // 购物车
    cart: {},           // {菜品名: 数量}
    cartCount: 0,
    cartTotal: 0,
    showCart: false,
    lang: i18n.current(),
    i18n: i18n.pack(i18n.current())
  },

  onLoad() {
    const lang = i18n.current();
    this.setData({ lang: lang, i18n: i18n.pack(lang) });
    this.loadMenu();
  },

  onShow() {
    // 从其它页面切了语言，回来要跟上（菜品已加载则就地重算文案）
    const lang = i18n.current();
    if (lang === this.data.lang) return;
    this.setData({ lang: lang, i18n: i18n.pack(lang) });
    if (this.data.categories.length) {
      this.setData({ categories: this.decorate(this.data.categories, lang) });
    } else if (!this.data.loading) {
      this.loadMenu();
    }
  },

  /** 语言开关 */
  toggleLang() {
    const lang = i18n.toggle();
    this.setData({
      lang: lang,
      i18n: i18n.pack(lang),
      categories: this.decorate(this.data.categories, lang),
      error: this.data.error ? i18n.pack(lang).loadFail : ''
    });
  },

  /** 给菜品补语言相关字段 */
  decorate(categories, lang) {
    return categories.map((cat) => ({
      name: cat.name,
      items: cat.items.map((d) =>
        Object.assign({}, d, {
          spicyText: i18n.spicyText(d.spicy, lang),
          showSpicy: !!d.spicy && d.spicy !== '不辣',
          showDesc: lang !== 'en' && !!d.description
        })
      )
    }));
  },

  loadMenu() {
    this.setData({ loading: true, error: '' });
    const lang = this.data.lang;
    api
      .getMenu()
      .then((data) => {
        if (!Array.isArray(data) || data.length === 0) {
          this.setData({ loading: false, error: i18n.pack(lang).menuEmpty });
          return;
        }
        // 按分类分组
        const grouped = this.groupByCategory(data);
        // 为每个菜品加上购物车数量字段
        grouped.forEach((cat) => {
          cat.items.forEach((dish) => {
            dish.cartQty = this.data.cart[dish.name] || 0;
          });
        });
        this.setData({
          categories: this.decorate(grouped, lang),
          activeCategory: grouped[0] ? grouped[0].name : '',
          loading: false
        });
      })
      .catch((err) => {
        console.error('加载菜单失败', err);
        this.setData({
          loading: false,
          error: err.message || i18n.pack(lang).loadFail
        });
      });
  },

  groupByCategory(items) {
    const map = {};
    const order = ['招牌必点', '凉菜', '热菜·川味', '热菜·清淡', '汤类', '主食', '饮品'];
    items.forEach((item) => {
      const cat = item['分类'] || '其他';
      if (!map[cat]) map[cat] = { name: cat, items: [] };
      map[cat].items.push({
        name: item['菜品'],
        price: item['价格'],
        priceNum: parseFloat(String(item['价格']).replace('¥', '')) || 0,
        spicy: item['辣度'],
        description: item['描述'],
        allergens: item['过敏原'],
        cartQty: 0
      });
    });
    return order
      .filter((n) => map[n])
      .map((n) => map[n])
      .concat(
        Object.keys(map)
          .filter((n) => order.indexOf(n) === -1)
          .map((n) => map[n])
      );
  },

  // 切换分类
  selectCategory(e) {
    const name = e.currentTarget.dataset.name;
    this.setData({ activeCategory: name });
  },

  // 加菜
  addDish(e) {
    const name = e.currentTarget.dataset.name;
    const price = parseFloat(e.currentTarget.dataset.price);
    const cart = Object.assign({}, this.data.cart);
    cart[name] = (cart[name] || 0) + 1;
    this.updateCart(cart);
    this.refreshCartQty();
  },

  // 减菜
  minusDish(e) {
    const name = e.currentTarget.dataset.name;
    const cart = Object.assign({}, this.data.cart);
    if (cart[name] > 1) {
      cart[name] = cart[name] - 1;
    } else {
      delete cart[name];
    }
    this.updateCart(cart);
    this.refreshCartQty();
  },

  // 更新购物车总价和数量
  updateCart(cart) {
    let count = 0;
    let total = 0;
    Object.keys(cart).forEach((name) => {
      count += cart[name];
      // 找价格
      const dish = this.findDishByName(name);
      if (dish) total += dish.priceNum * cart[name];
    });
    this.setData({
      cart: cart,
      cartCount: count,
      cartTotal: total
    });
  },

  // 刷新菜品卡片上的数量
  refreshCartQty() {
    const cats = this.data.categories.map((cat) => {
      const items = cat.items.map((dish) => {
        return Object.assign({}, dish, {
          cartQty: this.data.cart[dish.name] || 0
        });
      });
      return Object.assign({}, cat, { items: items });
    });
    this.setData({ categories: cats });
  },

  findDishByName(name) {
    for (const cat of this.data.categories) {
      for (const dish of cat.items) {
        if (dish.name === name) return dish;
      }
    }
    return null;
  },

  // 切换购物车浮窗
  toggleCart() {
    if (this.data.cartCount === 0) return;
    this.setData({ showCart: !this.data.showCart });
  },

  closeCart() {
    this.setData({ showCart: false });
  },

  // 清空购物车
  clearCart() {
    const t = this.data.i18n;
    wx.showModal({
      title: t.clearCartTitle,
      content: t.clearCartBody,
      confirmText: t.confirm,
      cancelText: t.cancel,
      success: (res) => {
        if (res.confirm) {
          this.updateCart({});
          this.refreshCartQty();
          this.setData({ showCart: false });
        }
      }
    });
  },

  // 提交订单（跳到 AI 页面让 AI 帮忙下单）
  submitOrder() {
    if (this.data.cartCount === 0) return;
    // 把购物车内容拼成一句话（英文下用英文前缀，菜名保持中文）
    const items = [];
    Object.keys(this.data.cart).forEach((name) => {
      items.push(`${name}×${this.data.cart[name]}`);
    });
    const orderText = this.data.i18n.orderPrefix + items.join('、');
    // 跳转到 chat 页面，自动填入这条消息
    wx.navigateTo({
      url: '/pages/chat/chat?prefill=' + encodeURIComponent(orderText)
    });
  },

  // 返回
  goBack() {
    wx.navigateBack();
  }
});
