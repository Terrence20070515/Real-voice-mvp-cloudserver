// pages/chat/chat.js
const api = require('../../api');
const util = require('../../utils/util');

// 检测 AI 回复里是否包含「下单成功」的关键词
function detectOrderInReply(text) {
  if (!text) return false;
  // 匹配「订单编号 ORDXXXX」「下单成功」「已为您下单」等
  return (
    /ORD\d{4}/.test(text) ||
    /下单成功/.test(text) ||
    /已为您下单/.test(text) ||
    /订单已创建/.test(text)
  );
}

Page({
  data: {
    messages: [],
    inputValue: '',
    sessionId: '',
    isLoading: false,
    showMenu: false,
    menuData: [],
    menuLoading: false,
    scrollToView: '',

    // 输入区域状态
    inputFocus: false,
    keyboardHeight: 0,
    showMorePanel: false,
    panelHeight: 0,  // +号面板实际高度（px）

    // 状态栏高度（动态获取）
    statusBarHeight: 20,  // 默认值，onLoad 时会更新
    inputBarHeight: 50,   // 输入栏总高度（含安全区）
    inputRowHeight: 50,   // 输入行内容高度（不含safe area）
    safeAreaBottom: 0,    // 底部安全区域高度
    navBarHeight: 64,     // 顶部导航栏总高度（statusBar + 内容）
    scrollHeight: 0,      // 聊天滚动区域高度（动态计算，核心！）

    // 「+」面板：快捷指令
    quickCommands: [
      { icon: '🌶️', text: '我吃辣的，没过敏' },
      { icon: '🚫', text: '不辣的菜有哪些？' },
      { icon: '⭐', text: '推荐几个招牌菜' },
      { icon: '💰', text: '人均 50 元以内' },
      { icon: '🥣', text: '来一份汤' },
      { icon: '🍚', text: '主食有什么' },
      { icon: '🥜', text: '我花生过敏' }
    ]
  },

  onLoad(options) {
    // 0. 动态计算各区域高度
    const sysInfo = wx.getSystemInfoSync();
    const statusBarHeight = sysInfo.statusBarHeight || 20;
    const rpxToPx = sysInfo.windowWidth / 750;
    // 输入行内容高度：~132rpx → px
    const inputRowH = Math.round(132 * rpxToPx);
    // 底部安全区域
    const safeAreaB = sysInfo.safeArea ? (sysInfo.screenHeight - sysInfo.safeArea.bottom) : 0;
    // 输入栏总高度（含安全区）
    const inputBarH = inputRowH + safeAreaB;
    // 导航栏总高度：状态栏 + 内容区（~80rpx）
    const navBarH = statusBarHeight + Math.round(80 * rpxToPx);
    // 滚动区可用高度 = 窗口高度 - 输入栏
    const scrollH = sysInfo.windowHeight - inputBarH;
    this.setData({ 
      statusBarHeight, 
      inputRowHeight: inputRowH,
      safeAreaBottom: safeAreaB,
      inputBarHeight: inputBarH,
      navBarHeight: navBarH,
      scrollHeight: scrollH
    });

    // 1. 获取 session_id（已持久化到 storage）
    const sessionId = util.getSessionId();
    this.setData({ sessionId });

    // 2. 恢复历史聊天记录（按 sessionId 存储）
    const savedMessages = util.loadChatHistory(sessionId);
    if (savedMessages && savedMessages.length > 0) {
      this.setData({ messages: savedMessages });
      this.scrollToBottom();
    } else {
      // 第一次进入，添加欢迎消息
      this.addMessage(
        '您好！我是川味小馆的 AI 点餐助手 🤖\n\n可以告诉我您想吃什么，比如「我想吃辣的」、「推荐几个菜」，或者直接说「来一份水煮鱼」。\n\n请问几位用餐？',
        'assistant'
      );
    }

    // 3. 预加载菜单
    this.loadMenuData();

    // 4. 如果是从菜单页跳过来，预填消息
    if (options && options.prefill) {
      const prefillText = decodeURIComponent(options.prefill);
      this.setData({ inputValue: prefillText });
      // 自动发送
      setTimeout(() => this.sendMsg(), 300);
    }

    // 5. 监听键盘高度变化
    this.keyboardListener = (res) => {
      if (res.height > 0) {
        // 键盘弹出：滚动区缩小（键盘替代了safeArea，只减inputRowHeight+keyboardHeight）
        const scrollH = wx.getSystemInfoSync().windowHeight - this.data.inputRowHeight - res.height;
        this.setData({
          keyboardHeight: res.height,
          showMorePanel: false,
          scrollHeight: scrollH
        });
        this.scrollToBottom();
      } else {
        // 键盘收起：恢复原始滚动区
        const scrollH = wx.getSystemInfoSync().windowHeight - this.data.inputBarHeight;
        this.setData({ keyboardHeight: 0, scrollHeight: scrollH });
      }
    };
    wx.onKeyboardHeightChange(this.keyboardListener);
  },

  onUnload() {
    if (this.keyboardListener) {
      wx.offKeyboardHeightChange(this.keyboardListener);
    }
    // 离开页面前保存聊天记录
    util.saveChatHistory(this.data.sessionId, this.data.messages);
  },

  onHide() {
    // 切到后台也保存
    util.saveChatHistory(this.data.sessionId, this.data.messages);
  },

  // ─── 菜单加载 ───
  loadMenuData() {
    if (this.data.menuLoading) return;
    this.setData({ menuLoading: true });
    api
      .getMenu()
      .then((data) => {
        const grouped = this.groupByCategory(data);
        this.setData({ menuData: grouped, menuLoading: false });
      })
      .catch((err) => {
        console.error('加载菜单失败', err);
        this.setData({ menuLoading: false });
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

  // ─── 输入框 ───
  onInput(e) {
    this.setData({ inputValue: e.detail.value });
  },

  onInputFocus() {
    this.setData({ inputFocus: true, showMorePanel: false });
    this.scrollToBottom();
  },

  onInputBlur() {
    this.setData({ inputFocus: false });
  },

  // 点击聊天区域：收起键盘和面板
  onChatAreaTap() {
    if (this.data.keyboardHeight > 0) {
      wx.hideKeyboard();
    }
    if (this.data.showMorePanel) {
      // 面板关闭时恢复滚动区高度
      const scrollH = wx.getSystemInfoSync().windowHeight - this.data.inputBarHeight;
      this.setData({ showMorePanel: false, panelHeight: 0, scrollHeight: scrollH });
    }
  },

  scrollToBottom() {
    const list = this.data.messages;
    if (list.length === 0) return;
    const last = list[list.length - 1];
    setTimeout(() => {
      this.setData({ scrollToView: last.id });
    }, 60);
  },

  // ─── 「+」面板 ───
  toggleMorePanel() {
    const show = !this.data.showMorePanel;
    const sysInfo = wx.getSystemInfoSync();
    const rpxToPx = sysInfo.windowWidth / 750;
    if (show) {
      wx.hideKeyboard();
      const panelH = Math.round(480 * rpxToPx);
      // 面板打开：滚动区再缩小 panelHeight
      const scrollH = sysInfo.windowHeight - this.data.inputBarHeight - panelH;
      this.setData({ showMorePanel: show, panelHeight: panelH, scrollHeight: scrollH });
    } else {
      // 面板关闭：恢复原始滚动区
      const scrollH = sysInfo.windowHeight - this.data.inputBarHeight;
      this.setData({ showMorePanel: show, panelHeight: 0, scrollHeight: scrollH });
    }
    this.scrollToBottom();
  },

  sendQuickCommand(e) {
    const text = e.currentTarget.dataset.text;
    this.setData({ inputValue: text, showMorePanel: false });
    setTimeout(() => this.sendMsg(), 80);
  },

  // ─── 发送消息 ───
  sendMsg() {
    const content = (this.data.inputValue || '').trim();
    if (!content || this.data.isLoading) return;

    this.addMessage(content, 'user');
    this.setData({ inputValue: '', isLoading: true });

    api
      .chat({ sessionId: this.data.sessionId, message: content })
      .then((reply) => {
        if (reply && reply.trim()) {
          // 检测是否包含订单信息
          const hasOrder = detectOrderInReply(reply);
          this.addMessage(reply, 'assistant', hasOrder);
        } else {
          this.addMessage('（AI 没有返回内容，请重试）', 'assistant');
        }
      })
      .catch((err) => {
        console.error('AI 对话失败', err);
        let hint = '⚠️ 网络开小差了';
        if (err && err.message) {
          if (err.message.indexOf('connect') >= 0 || err.message.indexOf('无法连接') >= 0) {
            hint = '⚠️ 无法连接后端服务\n\n请检查：\n1. 后端是否已启动（python main.py）\n2. config.js 里的 apiBaseUrl 是否正确（真机用局域网 IP）\n3. 手机和电脑是否在同一个 WiFi';
          } else if (err.message.indexOf('超时') >= 0) {
            hint = '⚠️ AI 思考太久啦，请稍后再试';
          } else {
            hint = '⚠️ ' + err.message;
          }
        }
        this.addMessage(hint, 'assistant');
      })
      .then(() => {
        this.setData({ isLoading: false });
        // 保存聊天记录
        util.saveChatHistory(this.data.sessionId, this.data.messages);
      });
  },

  // 添加一条消息到列表
  addMessage(content, role, hasOrder) {
    const time = util.formatTime();
    const newMsg = {
      id: 'msg_' + Date.now() + '_' + Math.floor(Math.random() * 10000),
      role: role,
      content: content,
      time: time,
      hasOrder: !!hasOrder
    };
    const messages = this.data.messages.concat([newMsg]);
    this.setData({
      messages: messages,
      scrollToView: newMsg.id
    });
    // 立即保存
    util.saveChatHistory(this.data.sessionId, messages);
  },

  // 跳转到买单页面
  goToPay() {
    wx.navigateTo({
      url: '/pages/pay/pay?session_id=' + this.data.sessionId
    });
  },

  // ─── 菜单弹窗 ───
  toggleMenu() {
    const show = !this.data.showMenu;
    this.setData({ showMenu: show });
    if (show && this.data.menuData.length === 0 && !this.data.menuLoading) {
      this.loadMenuData();
    }
  },

  closeMenu() {
    this.setData({ showMenu: false });
  },

  // ─── 清空对话 ───
  // 注意：只清 AI 对话记忆，不换 session_id，不影响已有订单
  // 「清台」（清订单+重置 session）在买单页操作
  clearChat() {
    wx.showModal({
      title: '清空对话',
      content: 'AI 会忘记之前的对话内容，但已下的订单不受影响。\n\n确定继续吗？',
      confirmText: '确定清空',
      confirmColor: '#d4232c',
      success: (res) => {
        if (!res.confirm) return;
        wx.showLoading({ title: '清除中...' });
        api
          .clearSession(this.data.sessionId)
          .then(() => {
            // 只清本地聊天记录，不换 session_id
            util.clearChatHistory(this.data.sessionId);
            this.setData({ messages: [] });
            this.addMessage(
              '✨ 对话已清空\n\n有什么可以帮您的？请问几位用餐？',
              'assistant'
            );
          })
          .catch((err) => {
            console.error('清空失败', err);
            wx.showToast({ title: '清除失败，请重试', icon: 'none' });
          })
          .then(() => {
            wx.hideLoading();
          });
      }
    });
  },

  // ─── 清台 / 换桌 ───
  // 顾客已离席：彻底重置（清账单 + 清 AI 记忆 + 换全新 session + 清本地记录）
  // 关键保证：重新生成 session_id，下一位顾客拿到的是「零历史」的全新会话，
  // 后端对话里绝不会残留上一轮的「是否加单」，AI 会直接从头问候、开始下一轮。
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
        // 1) 后端清账单 + 清 AI 记忆（尽力而为；失败也不影响下面的本地重置）
        api
          .clearOrders(oldSid)
          .catch((err) => {
            console.warn('后端清台未成功（本地仍会重置）', err);
          })
          .then(() => {
            // 2) 换全新的 session_id —— 这是「下一轮绝对干净」的根本保证
            const newSid = util.generateSessionId();
            util.saveSessionId(newSid);
            // 3) 清掉旧 session 的本地聊天记录
            util.clearChatHistory(oldSid);
            // 4) 重置界面为全新问候，开启下一轮对话
            this.setData({ sessionId: newSid, messages: [] });
            this.addMessage(
              '欢迎光临川味小馆 🤖\n\n我是您的 AI 点餐助手。请问几位用餐？有什么忌口或口味偏好吗？',
              'assistant'
            );
            wx.hideLoading();
            wx.showToast({ title: '清台完成，已为新客准备', icon: 'success' });
          });
      }
    });
  },

  goBack() {
    wx.navigateBack();
  }
});
