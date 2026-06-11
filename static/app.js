// State Management
let activeBrokers = [];
let portfolios = [];
let orderHistory = [];
let ipos = [];
let ipoApplications = [];

// Chart references to prevent canvas reuse errors
let globalChart = null;
const portfolioCharts = {};
let initialNetWorth = null;

// DOM Elements - Auth Screen
const authContainer = document.getElementById('auth-container');
const appContainer = document.getElementById('app-container');
const loginForm = document.getElementById('login-form');
const signupForm = document.getElementById('signup-form');
const loginError = document.getElementById('login-error');
const signupError = document.getElementById('signup-error');
const tabLoginBtn = document.getElementById('tab-login-btn');
const tabSignupBtn = document.getElementById('tab-signup-btn');
const logoutBtn = document.getElementById('logout-btn');
const userBadgeDisplay = document.getElementById('user-badge-display');
const userAvatarLbl = document.getElementById('user-avatar-lbl');
const userNameLbl = document.getElementById('user-name-lbl');

// DOM Elements - Dashboard
const connectBrokerBtn = document.getElementById('connect-broker-btn');
const emptyStateConnectBtn = document.getElementById('empty-state-connect-btn');
const connectModal = document.getElementById('connect-modal');
const closeModalBtn = document.getElementById('close-modal-btn');
const cancelModalBtn = document.getElementById('cancel-modal-btn');
const connectBrokerForm = document.getElementById('connect-broker-form');
const brokerSelect = document.getElementById('modal-broker-select');
const credentialsContainer = document.getElementById('credentials-fields-container');
const portfoliosGrid = document.getElementById('portfolios-grid');
const noPortfoliosState = document.getElementById('no-portfolios-state');

// IPO DOM Elements
const ipoModal = document.getElementById('ipo-modal');
const closeIpoModalBtn = document.getElementById('close-ipo-modal-btn');
const cancelIpoModalBtn = document.getElementById('cancel-ipo-modal-btn');
const ipoApplyForm = document.getElementById('ipo-apply-form');
const ipoModalBrokerSelect = document.getElementById('ipo-modal-broker-select');
const ipoModalLotsInput = document.getElementById('ipo-modal-lots');
const ipoModalPriceInput = document.getElementById('ipo-modal-price');
const ipoModalUpiInput = document.getElementById('ipo-modal-upi');
const ipoSummaryShares = document.getElementById('ipo-summary-shares');
const ipoSummaryAmount = document.getElementById('ipo-summary-amount');

// Navigation Tabs
const navDashboardBtn = document.getElementById('nav-dashboard-btn');
const navIpoBtn = document.getElementById('nav-ipo-btn');
const dashboardView = document.getElementById('dashboard-view');
const ipoView = document.getElementById('ipo-view');

// Stats Elements
const totalNetWorthEl = document.getElementById('total-net-worth');
const activeBrokersCountEl = document.getElementById('active-brokers-count');
const totalHoldingsCountEl = document.getElementById('total-holdings-count');
const netWorthTrendEl = document.getElementById('net-worth-trend');

// Trade Form Elements
const tradeForm = document.getElementById('trade-form');
const tradeBrokerSelect = document.getElementById('trade-broker');
const tradeSymbolInput = document.getElementById('trade-symbol');
const tradeQtyInput = document.getElementById('trade-qty');
const btnBuy = document.getElementById('btn-buy');
const btnSell = document.getElementById('btn-sell');
const quoteDisplay = document.getElementById('trade-quote-display');
const quoteLtpEl = document.getElementById('quote-ltp');
const quoteBidAskEl = document.getElementById('quote-bid-ask');

// History Element
const orderHistoryList = document.getElementById('order-history-list');
const statusIndicator = document.getElementById('status-indicator');
const statusLabel = document.getElementById('status-label');

// Initialize WebSocket & Polling Fallback
let ws = null;
let reconnectAttempts = 0;
let isVercelFallback = false;
let pollingInterval = null;

// Auth Header Helper
function getAuthHeaders() {
    const token = localStorage.getItem('token');
    return {
        'Authorization': `Bearer ${token}`,
        'Content-Type': 'application/json'
    };
}

// Check if response is Unauthorized (401)
async function handleApiResponse(response) {
    if (response.status === 401) {
        showToast('Session expired. Please login again.', 'error');
        handleLogout();
        throw new Error('Unauthorized');
    }
    return response;
}

document.addEventListener('DOMContentLoaded', () => {
    setupEventListeners();
    checkAuth();
});

// Authentication Gatekeeper
function checkAuth() {
    const token = localStorage.getItem('token');
    const username = localStorage.getItem('username');
    
    if (token) {
        // Authenticated: Show Dashboard, Hide Auth
        authContainer.style.display = 'none';
        appContainer.style.display = 'flex';
        
        // Update user badge
        if (username) {
            userBadgeDisplay.style.display = 'flex';
            userAvatarLbl.textContent = username.substring(0, 1).toUpperCase();
            userNameLbl.textContent = username;
        }
        
        // Connect services
        const isVercel = window.location.hostname.includes('vercel.app');
        if (isVercel) {
            console.log("Running on Vercel. Using HTTP polling directly.");
            isVercelFallback = true;
            fetchData();
            fetchIPOs();
            startPolling();
        } else {
            connectWebSocket();
            fetchIPOs();
        }
    } else {
        // Unauthenticated: Show Auth, Hide Dashboard
        authContainer.style.display = 'flex';
        appContainer.style.display = 'none';
        userBadgeDisplay.style.display = 'none';
        
        // Stop connections
        if (ws) {
            ws.close();
            ws = null;
        }
        if (pollingInterval) {
            clearInterval(pollingInterval);
            pollingInterval = null;
        }
    }
}

function startPolling() {
    if (pollingInterval) clearInterval(pollingInterval);
    pollingInterval = setInterval(fetchLiveQuotesAndValues, 4000);
}

function connectWebSocket() {
    const token = localStorage.getItem('token');
    if (!token) return;

    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/api/ws?token=${encodeURIComponent(token)}`;
    
    console.log(`Connecting to WebSocket: ${wsUrl}`);
    ws = new WebSocket(wsUrl);
    
    ws.onopen = () => {
        console.log('WebSocket connection established.');
        updateConnectionIndicator(true);
        reconnectAttempts = 0;
    };
    
    ws.onmessage = (event) => {
        try {
            const data = JSON.parse(event.data);
            if (data.type === 'initial') {
                portfolios = data.portfolios?.portfolios || [];
                activeBrokers = data.portfolios?.summary?.active_count > 0 ? portfolios.map(p => p.broker) : [];
                orderHistory = data.history || [];
                renderDashboard();
                fetchIPOs();
            } else if (data.type === 'update') {
                portfolios = data.portfolios?.portfolios || [];
                
                updateStatValues(data.portfolios?.summary);
                updateAllCharts();
                
                portfolios.forEach(p => {
                    const valuationAmtEl = document.getElementById(`val-${p.broker}`);
                    if (valuationAmtEl) {
                        if (p.error) {
                            valuationAmtEl.textContent = 'Error';
                        } else {
                            valuationAmtEl.textContent = formatCurrency(p.total_value, p.broker);
                        }
                    }
                    
                    if (p.holdings) {
                        p.holdings.forEach(h => {
                            const priceEl = document.getElementById(`price-${p.broker}-${h.symbol}`);
                            const valueEl = document.getElementById(`value-${p.broker}-${h.symbol}`);
                            if (priceEl && valueEl) {
                                priceEl.textContent = formatCurrency(h.current_price, p.broker);
                                valueEl.textContent = formatCurrency(h.qty * h.current_price, p.broker);
                            }
                        });
                    }
                });
                
                fetchQuickQuote();
            }
        } catch (err) {
            console.error('Error handling WebSocket message:', err);
        }
    };
    
    ws.onclose = (e) => {
        console.log(`WebSocket disconnected. Code: ${e.code}, Reason: ${e.reason}`);
        updateConnectionIndicator(false);
        
        // If token is missing, do not attempt reconnect
        if (!localStorage.getItem('token')) return;
        
        // Unauthorized ws rejection code
        if (e.code === 1008) {
            showToast('Session expired. Please log in again.', 'error');
            handleLogout();
            return;
        }

        if (reconnectAttempts > 3) {
            console.warn("WebSocket reconnection limit reached. Falling back to HTTP polling.");
            isVercelFallback = true;
            fetchData();
            startPolling();
            return;
        }
        
        const timeout = Math.min(1000 * Math.pow(2, reconnectAttempts), 10000);
        reconnectAttempts++;
        console.log(`Reconnecting WebSocket in ${timeout}ms...`);
        setTimeout(connectWebSocket, timeout);
    };
    
    ws.onerror = (err) => {
        console.error('WebSocket error:', err);
        ws.close();
    };
}

// Event Listeners Setup
function setupEventListeners() {
    // Auth Tab switching
    tabLoginBtn.addEventListener('click', () => {
        tabLoginBtn.classList.add('active');
        tabSignupBtn.classList.remove('active');
        loginForm.style.display = 'block';
        signupForm.style.display = 'none';
        loginError.style.display = 'none';
        signupError.style.display = 'none';
    });

    tabSignupBtn.addEventListener('click', () => {
        tabSignupBtn.classList.add('active');
        tabLoginBtn.classList.remove('active');
        signupForm.style.display = 'block';
        loginForm.style.display = 'none';
        loginError.style.display = 'none';
        signupError.style.display = 'none';
    });

    // Auth Form submissions
    loginForm.addEventListener('submit', handleLoginSubmit);
    signupForm.addEventListener('submit', handleSignupSubmit);
    logoutBtn.addEventListener('click', handleLogout);

    // Modal controls
    const openModal = () => {
        connectModal.style.display = 'flex';
        renderCredentialsFields();
    };
    const closeModal = () => {
        connectModal.style.display = 'none';
        connectBrokerForm.reset();
        credentialsContainer.innerHTML = '';
    };

    connectBrokerBtn.addEventListener('click', openModal);
    emptyStateConnectBtn.addEventListener('click', openModal);
    closeModalBtn.addEventListener('click', closeModal);
    cancelModalBtn.addEventListener('click', closeModal);
    
    // Close modal on click outside content
    connectModal.addEventListener('click', (e) => {
        if (e.target === connectModal) closeModal();
    });

    // Dynamic Credentials Fields based on broker selection
    brokerSelect.addEventListener('change', renderCredentialsFields);

    // Connect Broker Form Submit
    connectBrokerForm.addEventListener('submit', handleConnectBroker);

    // Quote lookup on typing symbol / choosing broker
    tradeSymbolInput.addEventListener('input', debounce(fetchQuickQuote, 500));
    tradeBrokerSelect.addEventListener('change', fetchQuickQuote);

    // Trade Operations
    btnBuy.addEventListener('click', () => handleTrade('BUY'));
    btnSell.addEventListener('click', () => handleTrade('SELL'));

    // Tab switching
    navDashboardBtn.addEventListener('click', () => switchTab('dashboard'));
    navIpoBtn.addEventListener('click', () => switchTab('ipo'));

    // IPO Modal events
    const closeIpoModal = () => {
        ipoModal.style.display = 'none';
        ipoApplyForm.reset();
    };
    closeIpoModalBtn.addEventListener('click', closeIpoModal);
    cancelIpoModalBtn.addEventListener('click', closeIpoModal);
    ipoModal.addEventListener('click', (e) => {
        if (e.target === ipoModal) closeIpoModal();
    });
    
    ipoModalLotsInput.addEventListener('input', updateIpoModalSummary);
    ipoModalPriceInput.addEventListener('input', updateIpoModalSummary);
    ipoApplyForm.addEventListener('submit', handleIPOApplicationSubmit);
}

// Auth Actions

async function handleLoginSubmit(e) {
    e.preventDefault();
    loginError.style.display = 'none';
    const email = document.getElementById('login-email').value;
    const password = document.getElementById('login-password').value;

    try {
        const res = await fetch('/api/auth/login', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ email, password })
        });
        const data = await res.json();
        
        if (res.ok) {
            localStorage.setItem('token', data.access_token);
            localStorage.setItem('username', data.user.username);
            localStorage.setItem('email', data.user.email);
            showToast('Logged in successfully!');
            checkAuth();
        } else {
            loginError.textContent = data.detail || 'Login failed. Please check credentials.';
            loginError.style.display = 'block';
        }
    } catch (err) {
        console.error('Login error:', err);
        loginError.textContent = 'Server connection issue.';
        loginError.style.display = 'block';
    }
}

async function handleSignupSubmit(e) {
    e.preventDefault();
    signupError.style.display = 'none';
    const username = document.getElementById('signup-username').value;
    const email = document.getElementById('signup-email').value;
    const password = document.getElementById('signup-password').value;

    try {
        const res = await fetch('/api/auth/register', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ email, username, password })
        });
        const data = await res.json();
        
        if (res.ok) {
            localStorage.setItem('token', data.access_token);
            localStorage.setItem('username', data.user.username);
            localStorage.setItem('email', data.user.email);
            showToast('Account created successfully!');
            checkAuth();
        } else {
            signupError.textContent = data.detail || 'Registration failed. Try again.';
            signupError.style.display = 'block';
        }
    } catch (err) {
        console.error('Signup error:', err);
        signupError.textContent = 'Server connection issue.';
        signupError.style.display = 'block';
    }
}

function handleLogout() {
    localStorage.removeItem('token');
    localStorage.removeItem('username');
    localStorage.removeItem('email');
    
    // Clear state
    activeBrokers = [];
    portfolios = [];
    orderHistory = [];
    ipos = [];
    ipoApplications = [];
    initialNetWorth = null;
    
    // Destroy charts
    if (globalChart) {
        globalChart.destroy();
        globalChart = null;
    }
    Object.keys(portfolioCharts).forEach(broker => {
        portfolioCharts[broker].destroy();
        delete portfolioCharts[broker];
    });
    
    checkAuth();
}

// Show Toast Notification
function showToast(message, type = 'success') {
    const container = document.getElementById('toast-container');
    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    
    const icon = type === 'success' ? '✓' : '⚠';
    toast.innerHTML = `<span>${icon}</span> <span>${message}</span>`;
    
    container.appendChild(toast);
    
    // Auto remove toast
    setTimeout(() => {
        toast.style.opacity = '0';
        toast.style.transform = 'translateY(20px)';
        setTimeout(() => toast.remove(), 300);
    }, 4000);
}

// Render dynamic forms for broker credentials
function renderCredentialsFields() {
    const broker = brokerSelect.value;
    credentialsContainer.innerHTML = '';

    if (!broker) return;

    let fieldsHTML = '';
    if (broker === 'Zerodha') {
        fieldsHTML = `
            <div class="form-group">
                <label for="cred-api-key">API Key</label>
                <input type="text" id="cred-api-key" placeholder="Enter Zerodha API Key" required>
            </div>
            <div class="form-group">
                <label for="cred-access-token">Access Token</label>
                <input type="password" id="cred-access-token" placeholder="Enter Kite Access Token" required>
            </div>
        `;
    } else if (broker === 'Alpaca') {
        fieldsHTML = `
            <div class="form-group">
                <label for="cred-api-key">API Key ID</label>
                <input type="text" id="cred-api-key" placeholder="Enter Alpaca API Key" required>
            </div>
            <div class="form-group">
                <label for="cred-secret-key">Secret Key</label>
                <input type="password" id="cred-secret-key" placeholder="Enter Alpaca Secret Key" required>
            </div>
        `;
    } else if (broker === 'Groww') {
        fieldsHTML = `
            <div class="form-group">
                <label for="cred-api-key">API Key</label>
                <input type="text" id="cred-api-key" placeholder="Enter Groww API Key" required>
            </div>
            <div class="form-group">
                <label for="cred-client-id">Client ID</label>
                <input type="text" id="cred-client-id" placeholder="Enter Groww Client ID" required>
            </div>
        `;
    } else if (broker === 'Motilal Oswal') {
        fieldsHTML = `
            <div class="form-group">
                <label for="cred-api-key">API Key</label>
                <input type="text" id="cred-api-key" placeholder="Enter Motilal Oswal API Key" required>
            </div>
            <div class="form-group">
                <label for="cred-client-id">Client ID</label>
                <input type="text" id="cred-client-id" placeholder="Enter Motilal Oswal Client ID" required>
            </div>
        `;
    }

    credentialsContainer.innerHTML = fieldsHTML;
}

// API Calls: Load all dashboard data
async function fetchData() {
    try {
        setLoadingState(true);
        
        // Fetch portfolios and active brokers
        const [brokersRes, portfoliosRes, historyRes] = await Promise.all([
            fetch('/api/brokers', { headers: getAuthHeaders() }).then(handleApiResponse).then(r => r.json()),
            fetch('/api/portfolios', { headers: getAuthHeaders() }).then(handleApiResponse).then(r => r.json()),
            fetch('/api/history', { headers: getAuthHeaders() }).then(handleApiResponse).then(r => r.json())
        ]);
        
        activeBrokers = portfoliosRes.summary?.active_count > 0 ? brokersRes.active : [];
        portfolios = portfoliosRes.portfolios || [];
        orderHistory = historyRes || [];

        updateConnectionIndicator(true);
        renderDashboard();
    } catch (error) {
        console.error('Error fetching data:', error);
        if (error.message !== 'Unauthorized') {
            updateConnectionIndicator(false);
            showToast('Failed to fetch data from API', 'error');
        }
    } finally {
        setLoadingState(false);
    }
}

// Live Quotes and Dynamic Values Ticker (called periodically)
async function fetchLiveQuotesAndValues() {
    if (activeBrokers.length === 0) return;
    try {
        const res = await fetch('/api/portfolios', { headers: getAuthHeaders() });
        await handleApiResponse(res);
        const portfoliosRes = await res.json();
        portfolios = portfoliosRes.portfolios || [];
        
        // Soft-update the values in the UI
        updateStatValues(portfoliosRes.summary);
        updateAllCharts();
        
        portfolios.forEach(p => {
            const valuationAmtEl = document.getElementById(`val-${p.broker}`);
            if (valuationAmtEl) {
                if (p.error) {
                    valuationAmtEl.textContent = 'Error';
                } else {
                    valuationAmtEl.textContent = formatCurrency(p.total_value, p.broker);
                }
            }
            
            if (p.holdings) {
                p.holdings.forEach(h => {
                    const priceEl = document.getElementById(`price-${p.broker}-${h.symbol}`);
                    const valueEl = document.getElementById(`value-${p.broker}-${h.symbol}`);
                    if (priceEl && valueEl) {
                        priceEl.textContent = formatCurrency(h.current_price, p.broker);
                        valueEl.textContent = formatCurrency(h.qty * h.current_price, p.broker);
                    }
                });
            }
        });
        
        fetchQuickQuote();
        
    } catch (e) {
        console.warn('Silent live ticker error:', e);
    }
}

function updateConnectionIndicator(connected) {
    if (connected) {
        statusIndicator.className = 'status-dot green';
        statusLabel.textContent = 'Server Connected';
    } else {
        statusIndicator.className = 'status-dot red';
        statusLabel.textContent = 'Disconnected';
    }
}

function setLoadingState(loading) {
    connectBrokerBtn.disabled = loading;
}

// Render Dashboard UI
function renderDashboard() {
    // 1. Update stats summary
    const totalVal = portfolios.reduce((sum, p) => sum + (p.total_value || 0), 0);
    updateStatValues({
        total_value: totalVal,
        active_count: activeBrokers.length
    });
    
    // 2. Clear grids
    portfoliosGrid.innerHTML = '';
    
    if (portfolios.length === 0) {
        portfoliosGrid.appendChild(noPortfoliosState);
        noPortfoliosState.style.display = 'flex';
        document.getElementById('global-chart-empty').style.display = 'flex';
        document.getElementById('global-allocation-chart').style.display = 'none';
        tradeBrokerSelect.innerHTML = '<option value="" disabled selected>Choose Broker...</option>';
        return;
    }
    
    noPortfoliosState.style.display = 'none';
    document.getElementById('global-chart-empty').style.display = 'none';
    document.getElementById('global-allocation-chart').style.display = 'block';

    // 3. Render side-by-side portfolios
    portfolios.forEach(portfolio => {
        const card = createPortfolioCard(portfolio);
        portfoliosGrid.appendChild(card);
        renderPortfolioDonut(portfolio);
    });

    // 4. Render Global Chart
    renderGlobalAllocationChart();

    // 5. Update Trade Form Broker List
    const selectedBrokerVal = tradeBrokerSelect.value;
    tradeBrokerSelect.innerHTML = '<option value="" disabled selected>Choose Broker...</option>';
    activeBrokers.forEach(name => {
        const opt = document.createElement('option');
        opt.value = name;
        opt.textContent = name;
        tradeBrokerSelect.appendChild(opt);
    });
    // Restore previous selection if still active
    if (activeBrokers.includes(selectedBrokerVal)) {
        tradeBrokerSelect.value = selectedBrokerVal;
    }

    // 6. Render Order History
    renderOrderHistory();
}

function updateStatValues(summary) {
    if (!summary) return;
    const currentNetWorth = summary.total_value || 0;
    totalNetWorthEl.textContent = formatCurrency(currentNetWorth, 'Global');
    activeBrokersCountEl.textContent = summary.active_count || 0;
    
    // Calculate total unique assets
    const uniqueAssets = new Set();
    portfolios.forEach(p => {
        if (p.holdings) {
            p.holdings.forEach(h => uniqueAssets.add(h.symbol));
        }
    });
    totalHoldingsCountEl.textContent = uniqueAssets.size;

    // Reset baseline if no active portfolios
    if (portfolios.length === 0) {
        initialNetWorth = null;
    }

    // Dynamically calculate session trend
    if (initialNetWorth === null || initialNetWorth === 0) {
        if (currentNetWorth > 0) {
            initialNetWorth = currentNetWorth;
        }
    }
    
    if (initialNetWorth > 0) {
        const percentChange = ((currentNetWorth - initialNetWorth) / initialNetWorth) * 100;
        const trendIcon = percentChange >= 0 ? '▲' : '▼';
        const trendText = `${percentChange >= 0 ? '+' : ''}${percentChange.toFixed(2)}% session`;
        
        netWorthTrendEl.className = `stat-trend ${percentChange < 0 ? 'negative' : ''}`;
        netWorthTrendEl.querySelector('.trend-icon').textContent = trendIcon;
        netWorthTrendEl.querySelector('.trend-value').textContent = trendText;
        netWorthTrendEl.style.display = 'flex';
    } else {
        netWorthTrendEl.style.display = 'none';
    }
}

// Create Card for Portfolio
function createPortfolioCard(portfolio) {
    const brokerName = portfolio.broker;
    
    const card = document.createElement('div');
    card.className = 'portfolio-card';
    card.id = `portfolio-card-${brokerName}`;

    // SVG Broker logos
    let logoSVG = '';
    if (brokerName === 'Zerodha') {
        logoSVG = `<svg viewBox="0 0 100 100" fill="none" xmlns="http://www.w3.org/2000/svg"><circle cx="50" cy="50" r="45" fill="#E33E33"/><rect x="30" y="30" width="40" height="40" rx="4" fill="white"/></svg>`;
    } else if (brokerName === 'Alpaca') {
        logoSVG = `<svg viewBox="0 0 100 100" fill="none" xmlns="http://www.w3.org/2000/svg"><circle cx="50" cy="50" r="45" fill="#FFC800"/><path d="M50 22L75 68H25L50 22Z" fill="black"/></svg>`;
    } else if (brokerName === 'Groww') {
        logoSVG = `<svg viewBox="0 0 100 100" fill="none" xmlns="http://www.w3.org/2000/svg"><circle cx="50" cy="50" r="45" fill="#00D09C"/><rect x="25" y="45" width="50" height="10" fill="white"/><rect x="45" y="25" width="10" height="50" fill="white"/></svg>`;
    } else if (brokerName === 'Motilal Oswal') {
        logoSVG = `<svg viewBox="0 0 100 100" fill="none" xmlns="http://www.w3.org/2000/svg"><circle cx="50" cy="50" r="45" fill="#1C3F94"/><path d="M30 35H70V45H55V65H45V45H30V35Z" fill="white"/></svg>`;
    }

    if (portfolio.error) {
        card.innerHTML = `
            <div class="portfolio-header">
                <div class="portfolio-info">
                    <div class="broker-logo">
                        ${logoSVG}
                    </div>
                    <div class="broker-details">
                        <h4>${brokerName}</h4>
                        <span class="broker-status" style="color: var(--color-danger);">
                            <span class="status-dot red" style="width: 6px; height: 6px;"></span> Connection Error
                        </span>
                    </div>
                </div>
                <div class="portfolio-valuation">
                    <span class="valuation-label">Account Value</span>
                    <div class="valuation-amount" id="val-${brokerName}" style="color: var(--color-danger); font-size: 18px;">Error</div>
                </div>
            </div>
            
            <div class="portfolio-body-layout" style="grid-template-columns: 1fr;">
                <div class="portfolio-error-state" style="padding: 20px; text-align: center; background: rgba(239, 68, 68, 0.04); border: 1px solid rgba(239, 68, 68, 0.12); border-radius: var(--radius-md); display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 8px;">
                    <span style="font-size: 22px;">⚠️</span>
                    <h5 style="font-family: var(--font-heading); font-size: 13px; font-weight: 700; color: var(--color-danger);">API Connection Failed</h5>
                    <p style="font-size: 12px; color: var(--text-muted); line-height: 1.4; max-width: 380px;">${portfolio.error}</p>
                </div>
            </div>
            
            <div class="portfolio-actions">
                <button class="btn btn-secondary btn-quick-trade" data-broker="${brokerName}" disabled style="opacity: 0.5; cursor: not-allowed;">
                    Trade
                </button>
                <button class="btn btn-danger-outline btn-disconnect" data-broker="${brokerName}">
                    Disconnect
                </button>
            </div>
        `;
    } else {
        const totalValStr = formatCurrency(portfolio.total_value, brokerName);
        
        let holdingsHTML = '';
        if (portfolio.holdings && portfolio.holdings.length > 0) {
            portfolio.holdings.forEach(h => {
                const formattedPrice = formatCurrency(h.current_price, brokerName);
                const formattedVal = formatCurrency(h.qty * h.current_price, brokerName);
                holdingsHTML += `
                    <tr>
                        <td><span class="symbol-tag">${h.symbol}</span></td>
                        <td class="number-col">${h.qty}</td>
                        <td class="number-col" id="price-${brokerName}-${h.symbol}">${formattedPrice}</td>
                        <td class="number-col" id="value-${brokerName}-${h.symbol}" style="font-weight: 600;">${formattedVal}</td>
                    </tr>
                `;
            });
        } else {
            holdingsHTML = `<tr><td colspan="4" style="text-align: center; color: var(--text-muted); font-style: italic; padding: 20px;">No holdings inside portfolio.</td></tr>`;
        }

        card.innerHTML = `
            <div class="portfolio-header">
                <div class="portfolio-info">
                    <div class="broker-logo">
                        ${logoSVG}
                    </div>
                    <div class="broker-details">
                        <h4>${brokerName}</h4>
                        <span class="broker-status">
                            <span class="status-dot green" style="width: 6px; height: 6px;"></span> Connected
                        </span>
                    </div>
                </div>
                <div class="portfolio-valuation">
                    <span class="valuation-label">Account Value</span>
                    <div class="valuation-amount" id="val-${brokerName}">${totalValStr}</div>
                </div>
            </div>
            
            <div class="portfolio-body-layout">
                <div class="holdings-table-wrapper">
                    <table class="holdings-table">
                        <thead>
                            <tr>
                                <th>Symbol</th>
                                <th class="number-col">Qty</th>
                                <th class="number-col">Price</th>
                                <th class="number-col">Value</th>
                            </tr>
                        </thead>
                        <tbody>
                            ${holdingsHTML}
                        </tbody>
                    </table>
                </div>
                
                <div class="mini-chart-container">
                    <canvas id="chart-${brokerName}"></canvas>
                </div>
            </div>
            
            <div class="portfolio-actions">
                <button class="btn btn-secondary btn-quick-trade" data-broker="${brokerName}">
                    Trade
                </button>
                <button class="btn btn-danger-outline btn-disconnect" data-broker="${brokerName}">
                    Disconnect
                </button>
            </div>
        `;
    }

    if (!portfolio.error) {
        card.querySelector('.btn-quick-trade').addEventListener('click', () => {
            tradeBrokerSelect.value = brokerName;
            tradeSymbolInput.focus();
            fetchQuickQuote();
        });
    }

    card.querySelector('.btn-disconnect').addEventListener('click', () => {
        handleDisconnectBroker(brokerName);
    });

    return card;
}

// Chart Rendering: Individual Broker Donut
function renderPortfolioDonut(portfolio) {
    const brokerName = portfolio.broker;
    const canvasId = `chart-${brokerName}`;
    const ctx = document.getElementById(canvasId)?.getContext('2d');
    if (!ctx) return;

    if (portfolioCharts[brokerName]) {
        portfolioCharts[brokerName].destroy();
    }

    const labels = portfolio.holdings?.map(h => h.symbol) || [];
    const data = portfolio.holdings?.map(h => h.qty * h.current_price) || [];
    
    if (labels.length === 0) {
        labels.push("Cash");
        data.push(1);
    }

    const colors = getHarmoniousColors(labels.length);

    portfolioCharts[brokerName] = new Chart(ctx, {
        type: 'doughnut',
        data: {
            labels: labels,
            datasets: [{
                data: data,
                backgroundColor: colors,
                borderWidth: 1,
                borderColor: 'rgba(15, 23, 42, 0.8)'
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { display: false },
                tooltip: {
                    callbacks: {
                        label: function(context) {
                            const val = context.raw;
                            return ` ${context.label}: ${formatCurrency(val, brokerName)}`;
                        }
                    }
                }
            },
            cutout: '65%'
        }
    });
}

// Chart Rendering: Global Combined Holdings Donut
function renderGlobalAllocationChart() {
    const ctx = document.getElementById('global-allocation-chart')?.getContext('2d');
    if (!ctx) return;

    if (globalChart) {
        globalChart.destroy();
    }

    const combinedData = {};
    portfolios.forEach(p => {
        p.holdings?.forEach(h => {
            const sym = h.symbol.toUpperCase();
            const conversionRate = (p.broker === 'Zerodha' || p.broker === 'Groww' || p.broker === 'Motilal Oswal') ? 0.0125 : 1.0;
            const assetValInUSD = h.qty * h.current_price * conversionRate;
            
            combinedData[sym] = (combinedData[sym] || 0) + assetValInUSD;
        });
    });

    const labels = Object.keys(combinedData);
    const data = Object.values(combinedData);

    if (labels.length === 0) {
        document.getElementById('global-chart-empty').style.display = 'flex';
        document.getElementById('global-allocation-chart').style.display = 'none';
        return;
    }

    const colors = getHarmoniousColors(labels.length);

    globalChart = new Chart(ctx, {
        type: 'pie',
        data: {
            labels: labels,
            datasets: [{
                data: data,
                backgroundColor: colors,
                borderWidth: 1,
                borderColor: 'rgba(15, 23, 42, 0.8)'
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    position: 'bottom',
                    labels: {
                        color: 'hsl(215, 25%, 75%)',
                        font: { family: 'Inter', size: 11 }
                    }
                },
                tooltip: {
                    callbacks: {
                        label: function(context) {
                            const val = context.raw;
                            return ` ${context.label}: $${val.toFixed(2)} (normalized USD)`;
                        }
                    }
                }
            }
        }
    });
}

function updateAllCharts() {
    portfolios.forEach(p => {
        const chart = portfolioCharts[p.broker];
        if (chart) {
            const data = p.holdings?.map(h => h.qty * h.current_price) || [1];
            chart.data.datasets[0].data = data;
            chart.update('none');
        }
    });
    
    if (globalChart) {
        const combinedData = {};
        portfolios.forEach(p => {
            p.holdings?.forEach(h => {
                const sym = h.symbol.toUpperCase();
                const conversionRate = (p.broker === 'Zerodha' || p.broker === 'Groww' || p.broker === 'Motilal Oswal') ? 0.0125 : 1.0;
                combinedData[sym] = (combinedData[sym] || 0) + (h.qty * h.current_price * conversionRate);
            });
        });
        
        globalChart.data.labels = Object.keys(combinedData);
        globalChart.data.datasets[0].data = Object.values(combinedData);
        globalChart.update('none');
    }
}

// Render Recent History list
function renderOrderHistory() {
    orderHistoryList.innerHTML = '';
    
    if (orderHistory.length === 0) {
        orderHistoryList.innerHTML = '<div class="history-empty">No orders logged yet.</div>';
        return;
    }

    orderHistory.slice(0, 10).forEach(order => {
        const item = document.createElement('div');
        item.className = 'history-item';
        
        const sideClass = order.side.toLowerCase() === 'buy' ? 'buy' : 'sell';
        const formattedPrice = formatCurrency(order.execution_price, order.broker);
        const totalCost = formatCurrency(order.qty * order.execution_price, order.broker);
        
        item.innerHTML = `
            <div class="history-item-top">
                <span class="history-symbol">${order.symbol}</span>
                <span class="history-action-badge ${sideClass}">${order.side}</span>
            </div>
            <div class="history-item-bottom">
                <span>${order.qty} shares @ ${formattedPrice}</span>
                <span style="font-weight: 600;">Total: ${totalCost}</span>
            </div>
            <div class="history-item-top" style="margin-top: 4px; border-top: 1px solid rgba(255,255,255,0.02); padding-top: 4px;">
                <span class="history-broker">${order.broker}</span>
                <span class="history-time">${formatTime(order.timestamp)}</span>
            </div>
        `;
        orderHistoryList.appendChild(item);
    });
}

// Action Handler: Connect Broker
async function handleConnectBroker(e) {
    e.preventDefault();
    const broker = brokerSelect.value;
    
    const credentials = {};
    if (broker === 'Zerodha') {
        credentials.api_key = document.getElementById('cred-api-key').value;
        credentials.access_token = document.getElementById('cred-access-token').value;
    } else if (broker === 'Alpaca') {
        credentials.api_key = document.getElementById('cred-api-key').value;
        credentials.secret_key = document.getElementById('cred-secret-key').value;
    } else if (broker === 'Groww') {
        credentials.api_key = document.getElementById('cred-api-key').value;
        credentials.client_id = document.getElementById('cred-client-id').value;
    } else if (broker === 'Motilal Oswal') {
        credentials.api_key = document.getElementById('cred-api-key').value;
        credentials.client_id = document.getElementById('cred-client-id').value;
    }

    try {
        const res = await fetch('/api/brokers', {
            method: 'POST',
            headers: getAuthHeaders(),
            body: JSON.stringify({ broker, credentials })
        });
        await handleApiResponse(res);
        const data = await res.json();
        
        if (res.ok) {
            showToast(`${broker} connected successfully!`);
            connectModal.style.display = 'none';
            connectBrokerForm.reset();
            credentialsContainer.innerHTML = '';
            fetchData();
        } else {
            showToast(data.detail || 'Connection failed', 'error');
        }
    } catch (err) {
        if (err.message !== 'Unauthorized') {
            console.error('Error connecting broker:', err);
            showToast('Server connection issue.', 'error');
        }
    }
}

// Action Handler: Disconnect Broker
async function handleDisconnectBroker(brokerName) {
    if (!confirm(`Are you sure you want to disconnect ${brokerName}?`)) return;
    try {
        const res = await fetch(`/api/brokers/${brokerName}`, { 
            method: 'DELETE',
            headers: getAuthHeaders()
        });
        await handleApiResponse(res);
        const data = await res.json();
        
        if (res.ok) {
            showToast(`${brokerName} disconnected.`);
            if (portfolioCharts[brokerName]) {
                portfolioCharts[brokerName].destroy();
                delete portfolioCharts[brokerName];
            }
            fetchData();
        } else {
            showToast(data.detail || 'Failed to disconnect', 'error');
        }
    } catch (err) {
        if (err.message !== 'Unauthorized') {
            console.error('Error disconnecting broker:', err);
            showToast('Server connection issue.', 'error');
        }
    }
}

// Action Handler: Quick Quote Fetch
async function fetchQuickQuote() {
    const broker = tradeBrokerSelect.value;
    const symbol = tradeSymbolInput.value.trim().toUpperCase();

    if (!broker || !symbol) {
        quoteDisplay.style.display = 'none';
        return;
    }

    try {
        const res = await fetch(`/api/quote/${broker}/${symbol}`, {
            headers: getAuthHeaders()
        });
        await handleApiResponse(res);
        if (res.ok) {
            const data = await res.json();
            quoteDisplay.style.display = 'block';
            quoteLtpEl.textContent = formatCurrency(data.ltp, broker);
            quoteBidAskEl.textContent = `${formatCurrency(data.bid, broker)} / ${formatCurrency(data.ask, broker)}`;
        } else {
            quoteDisplay.style.display = 'none';
        }
    } catch (err) {
        quoteDisplay.style.display = 'none';
    }
}

// Action Handler: Trade Submission (BUY/SELL)
async function handleTrade(side) {
    const broker = tradeBrokerSelect.value;
    const symbol = tradeSymbolInput.value.trim().toUpperCase();
    const qty = parseInt(tradeQtyInput.value);

    if (!broker) {
        showToast('Please select a broker', 'error');
        return;
    }
    if (!symbol) {
        showToast('Please specify a stock symbol', 'error');
        return;
    }
    if (!qty || qty <= 0) {
        showToast('Please enter a valid quantity', 'error');
        return;
    }

    try {
        const res = await fetch('/api/orders', {
            method: 'POST',
            headers: getAuthHeaders(),
            body: JSON.stringify({ broker, symbol, qty, side })
        });
        await handleApiResponse(res);
        const data = await res.json();
        
        if (res.ok) {
            showToast(`Order Placed: ${side} ${qty} ${symbol} on ${broker}`);
            tradeForm.reset();
            quoteDisplay.style.display = 'none';
            fetchData();
        } else {
            showToast(data.detail || 'Trade execution failed', 'error');
        }
    } catch (err) {
        if (err.message !== 'Unauthorized') {
            console.error('Trade placing error:', err);
            showToast('Server connection issue.', 'error');
        }
    }
}

// Helpers
function formatCurrency(val, broker) {
    if (typeof val !== 'number') return val;
    if (broker === 'Zerodha' || broker === 'Groww' || broker === 'Motilal Oswal') {
        return '₹' + val.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
    }
    return '$' + val.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function formatTime(timestampStr) {
    try {
        const parts = timestampStr.split(' ');
        if (parts.length > 1) return parts[1];
        return timestampStr;
    } catch (e) {
        return timestampStr;
    }
}

function getHarmoniousColors(count) {
    const baseColors = [
        'rgba(99, 102, 241, 0.8)',
        'rgba(168, 85, 247, 0.8)',
        'rgba(14, 165, 233, 0.8)',
        'rgba(16, 185, 129, 0.8)',
        'rgba(244, 63, 94, 0.8)',
        'rgba(245, 158, 11, 0.8)',
        'rgba(6, 182, 212, 0.8)',
        'rgba(236, 72, 153, 0.8)'
    ];
    
    const colors = [];
    for (let i = 0; i < count; i++) {
        colors.push(baseColors[i % baseColors.length]);
    }
    return colors;
}

function debounce(func, wait) {
    let timeout;
    return function executedFunction(...args) {
        const later = () => {
            clearTimeout(timeout);
            func(...args);
        };
        clearTimeout(timeout);
        timeout = setTimeout(later, wait);
    };
}

// IPO Portal functions
function switchTab(tab) {
    if (tab === 'dashboard') {
        navDashboardBtn.classList.add('active');
        navIpoBtn.classList.remove('active');
        dashboardView.style.display = 'block';
        ipoView.style.display = 'none';
    } else if (tab === 'ipo') {
        navDashboardBtn.classList.remove('active');
        navIpoBtn.classList.add('active');
        dashboardView.style.display = 'none';
        ipoView.style.display = 'block';
        fetchIPOs();
    }
}

async function fetchIPOs() {
    try {
        const [iposRes, appsRes] = await Promise.all([
            fetch('/api/ipos', { headers: getAuthHeaders() }).then(handleApiResponse).then(r => r.json()),
            fetch('/api/ipos/applications', { headers: getAuthHeaders() }).then(handleApiResponse).then(r => r.json())
        ]);
        ipos = iposRes || [];
        ipoApplications = appsRes || [];
        renderIPOs();
    } catch (err) {
        if (err.message !== 'Unauthorized') {
            console.error('Error fetching IPOs:', err);
        }
    }
}

function renderIPOs() {
    const openCount = ipos.filter(i => i.status === 'OPEN').length;
    const activeBidsCount = ipoApplications.filter(a => a.status === 'Applied').length;
    const totalInvestment = ipoApplications.reduce((sum, a) => sum + (a.amount || 0), 0);
    
    document.getElementById('open-ipos-count').textContent = openCount;
    document.getElementById('my-active-bids-count').textContent = activeBidsCount;
    document.getElementById('my-total-ipo-investment').textContent = '₹' + totalInvestment.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
    
    const iposGrid = document.getElementById('ipos-grid');
    iposGrid.innerHTML = '';
    
    if (ipos.length === 0) {
        iposGrid.innerHTML = '<div class="empty-state"><h4>No IPOs listed</h4></div>';
    } else {
        ipos.forEach(ipo => {
            const card = document.createElement('div');
            card.className = 'portfolio-card ipo-card';
            
            let statusClass = 'tag-upcoming';
            if (ipo.status === 'OPEN') statusClass = 'tag-open';
            else if (ipo.status === 'CLOSED') statusClass = 'tag-closed';
            
            const minInv = ipo.lot_size * ipo.min_price;
            const formattedMinInv = '₹' + minInv.toLocaleString('en-IN', { maximumFractionDigits: 0 });
            
            card.innerHTML = `
                <div class="portfolio-header">
                    <div class="broker-details" style="margin-left: 0;">
                        <h4>${ipo.company_name}</h4>
                        <span class="ipo-tag ${statusClass}">${ipo.status}</span>
                    </div>
                    <div class="portfolio-valuation" style="text-align: right;">
                        <span class="valuation-label">Price Band</span>
                        <div class="valuation-amount" style="font-size: 16px;">${ipo.price_range}</div>
                    </div>
                </div>
                <div class="portfolio-body-layout" style="grid-template-columns: 1fr; gap: 12px; margin-top: 16px;">
                    <div style="display: flex; justify-content: space-between; font-size: 13px; color: var(--text-secondary);">
                        <span>Lot Size:</span>
                        <span style="font-weight: 600;">${ipo.lot_size} Shares</span>
                    </div>
                    <div style="display: flex; justify-content: space-between; font-size: 13px; color: var(--text-secondary);">
                        <span>Min. Investment:</span>
                        <span style="font-weight: 600; color: var(--text-primary);">${formattedMinInv}</span>
                    </div>
                    <div style="display: flex; justify-content: space-between; font-size: 13px; color: var(--text-secondary);">
                        <span>Subscription Rate:</span>
                        <span style="font-weight: 600; color: var(--color-buy);">${ipo.subscribed}</span>
                    </div>
                    <div style="display: flex; justify-content: space-between; font-size: 13px; color: var(--text-secondary);">
                        <span>Bidding Window:</span>
                        <span style="font-size: 12px; font-weight: 500;">${ipo.open_date} to ${ipo.close_date}</span>
                    </div>
                </div>
                <div class="portfolio-actions" style="margin-top: 16px;">
                    <button class="btn btn-primary btn-apply-ipo" data-symbol="${ipo.symbol}" ${ipo.status !== 'OPEN' ? 'disabled style="opacity:0.5; cursor:not-allowed;"' : ''}>
                        Apply Now
                    </button>
                </div>
            `;
            
            if (ipo.status === 'OPEN') {
                card.querySelector('.btn-apply-ipo').addEventListener('click', () => openIPOModal(ipo));
            }
            iposGrid.appendChild(card);
        });
    }
    
    const listEl = document.getElementById('ipo-applications-list');
    listEl.innerHTML = '';
    
    if (ipoApplications.length === 0) {
        listEl.innerHTML = '<div class="history-empty">No IPO applications submitted yet.</div>';
    } else {
        ipoApplications.forEach(app => {
            const item = document.createElement('div');
            item.className = 'history-item';
            
            const formattedAmt = '₹' + app.amount.toLocaleString('en-IN', { minimumFractionDigits: 2 });
            const formattedPrice = '₹' + app.bid_price.toLocaleString('en-IN', { minimumFractionDigits: 2 });
            
            item.innerHTML = `
                <div class="history-item-top">
                    <span class="history-symbol" style="font-weight:700;">${app.ipo_symbol}</span>
                    <span class="history-action-badge buy">${app.status}</span>
                </div>
                <div class="history-item-bottom" style="margin-top: 4px; font-size: 12px; color: var(--text-secondary);">
                    <span>${app.lots} Lot(s) (${app.shares} shares) @ ${formattedPrice}</span>
                    <span style="font-weight:600; color: var(--text-primary);">Total: ${formattedAmt}</span>
                </div>
                <div class="history-item-bottom" style="margin-top: 4px; font-size: 11px; color: var(--text-muted);">
                    <span>Broker: ${app.broker} | UPI: ${app.upi_id}</span>
                    <span>ID: ${app.id}</span>
                </div>
                <div class="history-item-top" style="margin-top: 6px; border-top: 1px solid rgba(255,255,255,0.03); padding-top: 6px;">
                    <span class="history-time" style="font-size:11px;">${app.timestamp}</span>
                    <button class="btn btn-danger-outline btn-cancel-ipo-bid" data-id="${app.id}" style="padding: 2px 8px; font-size: 11px; height: auto;">Cancel Bid</button>
                </div>
            `;
            
            item.querySelector('.btn-cancel-ipo-bid').addEventListener('click', () => cancelIPOBid(app.id));
            listEl.appendChild(item);
        });
    }
}

function openIPOModal(ipo) {
    document.getElementById('ipo-modal-title').textContent = `Apply for ${ipo.company_name} IPO`;
    document.getElementById('ipo-modal-symbol').value = ipo.symbol;
    document.getElementById('ipo-modal-lot-size').textContent = `${ipo.lot_size} Shares`;
    document.getElementById('ipo-modal-price-range').textContent = ipo.price_range;
    
    ipoModalLotsInput.value = 1;
    ipoModalPriceInput.value = ipo.max_price;
    ipoModalPriceInput.min = ipo.min_price;
    ipoModalPriceInput.max = ipo.max_price;
    
    ipoModalBrokerSelect.innerHTML = '<option value="" disabled selected>Choose Broker...</option>';
    activeBrokers.forEach(name => {
        const opt = document.createElement('option');
        opt.value = name;
        opt.textContent = name;
        ipoModalBrokerSelect.appendChild(opt);
    });
    
    updateIpoModalSummary();
    ipoModal.style.display = 'flex';
}

function updateIpoModalSummary() {
    const symbol = document.getElementById('ipo-modal-symbol').value;
    const ipo = ipos.find(i => i.symbol === symbol);
    if (!ipo) return;
    
    const lots = parseInt(ipoModalLotsInput.value) || 0;
    const price = parseFloat(ipoModalPriceInput.value) || 0;
    
    const shares = lots * ipo.lot_size;
    const amount = shares * price;
    
    ipoSummaryShares.textContent = shares;
    ipoSummaryAmount.textContent = '₹' + amount.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

async function handleIPOApplicationSubmit(e) {
    e.preventDefault();
    const broker = ipoModalBrokerSelect.value;
    const ipo_symbol = document.getElementById('ipo-modal-symbol').value;
    const lots = parseInt(ipoModalLotsInput.value);
    const bid_price = parseFloat(ipoModalPriceInput.value);
    const upi_id = ipoModalUpiInput.value.trim();
    
    if (!broker) {
        showToast('Please select a connected broker.', 'error');
        return;
    }
    if (!upi_id) {
        showToast('Please enter your UPI ID.', 'error');
        return;
    }
    
    try {
        const res = await fetch('/api/ipos/apply', {
            method: 'POST',
            headers: getAuthHeaders(),
            body: JSON.stringify({ broker, ipo_symbol, lots, bid_price, upi_id })
        });
        await handleApiResponse(res);
        const data = await res.json();
        
        if (res.ok) {
            showToast(`IPO Bid Submitted: ${lots} lots for ${ipo_symbol} via ${broker}`);
            ipoModal.style.display = 'none';
            ipoApplyForm.reset();
            fetchIPOs();
        } else {
            showToast(data.detail || 'IPO Application failed', 'error');
        }
    } catch (err) {
        if (err.message !== 'Unauthorized') {
            console.error('IPO Apply Error:', err);
            showToast('Server connection issue.', 'error');
        }
    }
}

async function cancelIPOBid(appId) {
    if (!confirm('Are you sure you want to cancel this IPO bid?')) return;
    try {
        const res = await fetch(`/api/ipos/applications/${appId}`, { 
            method: 'DELETE',
            headers: getAuthHeaders()
        });
        await handleApiResponse(res);
        if (res.ok) {
            showToast('IPO bid cancelled.');
            fetchIPOs();
        } else {
            const data = await res.json();
            showToast(data.detail || 'Failed to cancel IPO bid', 'error');
        }
    } catch (err) {
        if (err.message !== 'Unauthorized') {
            console.error('Error cancelling IPO bid:', err);
            showToast('Server connection issue.', 'error');
        }
    }
}
