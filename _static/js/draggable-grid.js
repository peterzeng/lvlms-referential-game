// DraggableGrid JavaScript
// This file handles the draggable grid functionality for the experiment

class DraggableGrid {
    constructor(config) {
        this.isDirector = config.isDirector;
        this.chatMessages = config.chatMessages || [];
        this.partnerMessages = config.partnerMessages || [];
        this.typingTimeout = null;
        this.lastTypingSentAt = 0;
        this.TYPING_DEBOUNCE_MS = 200; // Reduced from 400ms for more responsive typing indicator
        this.TYPING_STOP_MS = 1000; // Reduced from 1500ms for faster clearing
        
        // Sound notification settings
        this.soundEnabled = true;
        this.messageSound = null;
        
        // Detect deployment environment
        this.isDeployed = this.detectDeploymentEnvironment();
        
        // Handle both cases: DOM already loaded or still loading
        if (document.readyState === 'loading') {
            document.addEventListener('DOMContentLoaded', () => {
                this.initialize();
            });
        } else {
            // DOM already loaded, initialize immediately
            this.initialize();
        }
    }
    
    // Detect if we're running in a deployed environment vs localhost
    detectDeploymentEnvironment() {
        const hostname = window.location.hostname;
        const isLocalhost = hostname === 'localhost' || hostname === '127.0.0.1' || hostname === '0.0.0.0';
        const isOtreeZip = window.location.pathname.includes('otree') || 
                          document.querySelector('meta[name="otree"]') !== null;
        
        if (console && console.log) {
            console.log(`Environment detection: hostname=${hostname}, isLocalhost=${isLocalhost}, isOtreeZip=${isOtreeZip}`);
        }
        
        return !isLocalhost || isOtreeZip;
    }
  goToNextPage() {
    try {
      const form = document.querySelector('form');
      if (form && typeof form.requestSubmit === 'function') {
        form.requestSubmit();
        return;
      }
      if (form) {
        form.submit();
        return;
      }
      const nextBtn = document.querySelector('button[type="submit"], input[type="submit"], .otree-next, button.otree-next, [name="next"]');
      if (nextBtn) {
        nextBtn.click();
      }
    } catch (_) {
      // no-op
    }
  }
    initialize() {
        this.setupChat();
        this.loadChatMessages();
        this.initializeSounds();
        this.setupBasketRefocus();
        this.initializeMagnifier();
        
        // Initialize chat height with multiple attempts to ensure it works in all environments
        this.initializeChatHeight();
        
        // Keep chat height synchronized with left grid area
        window.addEventListener('load', () => this.syncChatHeightToGrid());
        window.addEventListener('resize', () => this.syncChatHeightToGrid());
        this.setupHeightSyncObservers();
        
        // Debug info for typing indicator
        if (console && console.log) {
            console.log('DraggableGrid initialized with typing indicator support');
            console.log('Player role:', this.isDirector ? 'Director' : 'Matcher');
        }
    }
    
    // Initialize chat height with multiple attempts to handle different deployment environments
    initializeChatHeight() {
        // Strategy 1: Immediate sync (works in fast environments)
        this.syncChatHeightToGrid();
        
        // Strategy 2: DOM ready state check
        if (document.readyState === 'loading') {
            document.addEventListener('DOMContentLoaded', () => {
                setTimeout(() => this.syncChatHeightToGrid(), 50);
            });
        }
        
        // Strategy 3: Multiple timed attempts for slow-loading environments
        const attempts = [100, 300, 600, 1000, 2000];
        attempts.forEach(delay => {
            setTimeout(() => this.syncChatHeightToGrid(), delay);
        });
        
        // Strategy 4: Window load event (final fallback)
        window.addEventListener('load', () => {
            setTimeout(() => this.syncChatHeightToGrid(), 200);
        });
        
        // Strategy 5: Intersection Observer for when elements become visible
        if (typeof IntersectionObserver !== 'undefined') {
            const observer = new IntersectionObserver((entries) => {
                entries.forEach(entry => {
                    if (entry.isIntersecting) {
                        setTimeout(() => this.syncChatHeightToGrid(), 100);
                    }
                });
            });
            
            const chatPanel = document.querySelector('.chat-panel');
            if (chatPanel) {
                observer.observe(chatPanel);
            }
        }
    }
    
    initializeSounds() {
        try {
            // Create audio context for better sound control
            this.audioContext = new (window.AudioContext || window.webkitAudioContext)();
            // Resume the audio context on first user interaction (required by some browsers in prod)
            if (this.audioContext && this.audioContext.state === 'suspended') {
                const resumeOnce = () => {
                    try { this.audioContext.resume(); } catch (_) { /* no-op */ }
                };
                ['click', 'keydown', 'touchstart'].forEach(evt => {
                    window.addEventListener(evt, resumeOnce, { once: true, passive: true });
                });
            }
            
            // Only generate message sound - no typing sound
            this.messageSound = this.createPingSound(800, 0.3); // 800Hz, 0.3 seconds
            
            console.log('🔊 Sound system initialized successfully (message notifications only)');
        } catch (error) {
            console.warn('🔇 Could not initialize audio context:', error);
            this.soundEnabled = false;
        }
    }
    
    createPingSound(frequency, duration) {
        return () => {
            if (!this.soundEnabled || !this.audioContext) return;
            
            try {
                const oscillator = this.audioContext.createOscillator();
                const gainNode = this.audioContext.createGain();
                
                oscillator.connect(gainNode);
                gainNode.connect(this.audioContext.destination);
                
                oscillator.frequency.setValueAtTime(frequency, this.audioContext.currentTime);
                oscillator.type = 'sine';
                
                gainNode.gain.setValueAtTime(0.3, this.audioContext.currentTime);
                gainNode.gain.exponentialRampToValueAtTime(0.01, this.audioContext.currentTime + duration);
                
                oscillator.start(this.audioContext.currentTime);
                oscillator.stop(this.audioContext.currentTime + duration);
                
                console.log('🔊 Ping sound played');
            } catch (error) {
                console.warn('🔇 Error playing sound:', error);
            }
        };
    }
    
    playMessageSound() {
        if (this.messageSound) {
            this.messageSound();
        }
    }
    

    
    toggleSound() {
        // Sound is enforced; do not allow disabling.
        this.soundEnabled = true;
        return true;
    }
    
    // Debug method for troubleshooting typing indicator
    debugTypingIndicator() {
        console.log('Typing indicator debug info:');
        console.log('- isDirector:', this.isDirector);
        console.log('- TYPING_DEBOUNCE_MS:', this.TYPING_DEBOUNCE_MS);
        console.log('- TYPING_STOP_MS:', this.TYPING_STOP_MS);
        console.log('- liveSend available:', typeof liveSend === 'function');
        console.log('- typing indicator element:', document.getElementById('typing-indicator'));
    }
    setupChat() {
        const chatInput = document.getElementById('chat-input');
        const sendButton = document.getElementById('send-message-btn');
        const soundToggleBtn = document.getElementById('sound-toggle-btn');
        
        if (chatInput) {
            // Typing detection events
            chatInput.addEventListener('keypress', (e) => {
                if (e.key === 'Enter') {
                    this.sendMessage();
                }
            });
            
            chatInput.addEventListener('input', () => this.handleTyping());
            chatInput.addEventListener('focus', () => this.handleTyping());
            chatInput.addEventListener('blur', () => this.sendTyping(false));
            
            // Additional events for better typing detection
            chatInput.addEventListener('keydown', () => this.handleTyping());
            chatInput.addEventListener('paste', () => this.handleTyping());
            
            // Clear typing indicator when input is cleared
            chatInput.addEventListener('change', () => {
                if (!chatInput.value.trim()) {
                    this.sendTyping(false);
                }
            });
        }
        
        if (sendButton) {
            sendButton.addEventListener('click', () => {
                this.sendMessage();
            });
        }
        
        // Sound control is enforced on; no toggle UI.
    }
    handleTyping() {
        const now = Date.now();
        if (now - this.lastTypingSentAt > this.TYPING_DEBOUNCE_MS) {
            this.sendTyping(true);
            this.lastTypingSentAt = now;
        }
        clearTimeout(this.typingTimeout);
        this.typingTimeout = setTimeout(() => this.sendTyping(false), this.TYPING_STOP_MS);
    }
    sendTyping(isTyping) {
        try {
            console.log(`🔄 Sending typing status: ${isTyping ? 'STARTED' : 'STOPPED'}`);
            console.log(`👤 Player role: ${this.isDirector ? 'Director' : 'Matcher'}`);
            
            // Check if liveSend is available
            if (typeof liveSend === 'function') {
                const typingData = {
                    'typing': true,
                    'is_typing': !!isTyping,
                    'sender_role': this.isDirector ? 'director' : 'matcher',
                    'timestamp': new Date().toISOString(),
                };
                console.log('📤 Sending to server:', typingData);
                liveSend(typingData);
                console.log('✅ Typing status sent successfully');
            } else {
                console.error('❌ liveSend function not available!');
                console.warn('This means oTree live updates are not working properly.');
            }
        } catch (error) {
            console.error('❌ Error sending typing indicator:', error);
        }
    }
    sendMessage() {
        const input = document.getElementById('chat-input');
        const message = input.value.trim();
        if (message) {
            // Check for URLs in the message
            const urlPattern = /(https?:\/\/|www\.|\w+\.(com|org|net|edu|gov|io|co|uk|de|fr|app|ai))/i;
            if (urlPattern.test(message)) {
                alert('Sending links is not allowed in the chat.');
                return;
            }
            
            const timestamp = new Date().toISOString();
            // Display own message immediately
            this.displayMessage({
                text: message,
                timestamp: timestamp,
                sender_role: this.isDirector ? 'director' : 'matcher',
                isOwn: true
            });
            liveSend({
                'send_message': true,
                'message': message,
                'timestamp': timestamp,
                'is_guess': false
            });
            // Clear typing indicator for partner
            this.sendTyping(false);
            input.value = '';
        }
    }
    loadChatMessages() {
        const chatContainer = document.getElementById('chat-messages');
        if (!chatContainer) return;
        let allMessages = [];
        this.chatMessages.forEach(msg => {
            allMessages.push({...msg, isOwn: true});
        });
        this.partnerMessages.forEach(msg => {
            allMessages.push({...msg, isOwn: false});
        });
        allMessages.sort((a, b) => new Date(a.timestamp) - new Date(b.timestamp));
        chatContainer.innerHTML = '';
        allMessages.forEach(msg => {
            this.displayMessage(msg);
        });
        chatContainer.scrollTop = chatContainer.scrollHeight;
    }
    displayMessage(msg) {
        const chatContainer = document.getElementById('chat-messages');
        if (!chatContainer) return;
        const messageDiv = document.createElement('div');
        messageDiv.className = `chat-message ${msg.sender_role}`;
        if (msg.isOwn) {
            messageDiv.classList.add('own');
        }
        // Render compact message: sender and text on one line; timestamp hidden (kept for screen readers)
        const timestamp = new Date(msg.timestamp).toLocaleTimeString();
        messageDiv.innerHTML = `
            <span class="sender">${msg.sender_role === 'director' ? 'Director' : 'Matcher'}</span>
            <span class="text">${this.escapeHtml(msg.text)}</span>
            <span class="timestamp" aria-hidden="true">${timestamp}</span>
        `;
        chatContainer.appendChild(messageDiv);
        chatContainer.scrollTop = chatContainer.scrollHeight;
        // Note: Removed syncChatHeightToGrid() call to prevent continuous expansion
    }
    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }
    // Make chat panel height equal to the left column (grid) height so bottoms align
    syncChatHeightToGrid() {
        try {
            const chatPanel = document.querySelector('.chat-panel');
            if (!chatPanel) return;

            // Wait for DOM to be fully ready
            if (document.readyState !== 'complete') {
                setTimeout(() => this.syncChatHeightToGrid(), 100);
                return;
            }

            // Role-aware calculation:
            // - Matcher: match left column height so bottoms align with grid
            // - Director: use a consistent viewport-based height so it doesn't shrink
            const leftColumn = document.querySelector('.col-lg-8, .col-md-7');
            let desiredHeightPx = 0;
            if (!this.isDirector) {
                if (leftColumn && leftColumn.getBoundingClientRect().height > 0) {
                    const leftRect = leftColumn.getBoundingClientRect();
                    desiredHeightPx = Math.round(leftRect.height);
                } else {
                    const viewportHeight = window.innerHeight;
                    const headerEstimate = 140;
                    desiredHeightPx = Math.round((viewportHeight - headerEstimate) * 0.8);
                }
            } else {
                // Director: choose a generous, stable viewport-based height
                const viewportHeight = window.innerHeight;
                const headerEstimate = 140; // director has slightly more header content
                desiredHeightPx = Math.round((viewportHeight - headerEstimate) * 0.8);
            }
            
            // Set reasonable bounds
            const minHeight = 300;
            const maxHeight = Math.round(window.innerHeight * 0.9);
            desiredHeightPx = Math.max(minHeight, Math.min(desiredHeightPx, maxHeight));
            
            // Apply the height
            chatPanel.style.setProperty('height', `${desiredHeightPx}px`, 'important');
            
            // Debug logging for troubleshooting
            if (console && console.log) {
                console.log(`Chat height synced to: ${desiredHeightPx}px (min: ${minHeight}, max: ${maxHeight})`);
                console.log(`Chat panel computed height: ${chatPanel.getBoundingClientRect().height}px`);
            }
        } catch (error) {
            console.warn('Error syncing chat height:', error);
            // Emergency fallback: set a fixed reasonable height
            const chatPanel = document.querySelector('.chat-panel');
            if (chatPanel) {
                chatPanel.style.setProperty('height', '500px', 'important');
            }
        }
    }
    // Observe size changes in the main row container and resync height (both roles)
    setupHeightSyncObservers() {
        try {
            if (typeof ResizeObserver === 'undefined') return;
            const leftColumn = document.querySelector('.col-lg-8, .col-md-7');
            if (!leftColumn) return;
            
            let lastHeight = 0;
            const debouncedSync = () => {
                clearTimeout(this._syncTimer);
                this._syncTimer = setTimeout(() => {
                    const currentHeight = leftColumn.getBoundingClientRect().height;
                    // Only sync if height changed significantly (more than 10px)
                    if (Math.abs(currentHeight - lastHeight) > 10) {
                        this.syncChatHeightToGrid();
                        lastHeight = currentHeight;
                    }
                }, 100); // Increased debounce time
            };
            this._resizeObserver = new ResizeObserver(debouncedSync);
            this._resizeObserver.observe(leftColumn);
        } catch (error) {
            console.warn('Error setting up height sync observer:', error);
        }
    }
    handleLiveUpdate(data) {
        // Get the response data for this player
        const myId = window.js_vars.my_id;
        const myData = data[myId] || data;  // Fallback to data if not player-specific

        if (myData.advance_round) {
            this.goToNextPage();
            return;
        }
        
        if (myData.success) {
            if (myData.broadcast) {
                if (myData.new_message) {
                    // Only display partner messages from live updates
                    // (own messages are displayed immediately when sent)
                    const isOwnMessage = myData.new_message.sender_role === (this.isDirector ? 'director' : 'matcher');
                    if (!isOwnMessage) {
                        this.displayMessage({...myData.new_message, isOwn: false});
                        // Play message sound for partner messages
                        this.playMessageSound();
                    }
                }
                if (typeof myData.partner_typing === 'boolean') {
                    this.setTypingIndicator(myData.partner_typing, myData.partner_role);
                    // No typing sound - only message sounds
                }
                if (myData.task_complete && document.getElementById('submit-guess-btn')) {
                    document.getElementById('submit-guess-btn').disabled = true;
                }
            } else {
                this.showStatus(myData.message || 'Action completed!', 'success');
            }
        } else {
            this.showStatus(myData.message || 'Error occurred', 'error');
        }
    }
    showStatus(message, type) {
        const statusElement = document.getElementById('status-message');
        if (!statusElement) return;
        statusElement.textContent = message;
        statusElement.className = `ms-3 ${type}`;
        setTimeout(() => {
            statusElement.textContent = '';
            statusElement.className = 'ms-3 text-muted';
        }, 3000);
    }
    setTypingIndicator(isTyping, role) {
        const el = document.getElementById('typing-indicator');
        if (!el) return;
        
        if (isTyping) {
            const label = role === 'director' ? 'Director is typing…' : 'Matcher is typing…';
            el.innerHTML = `<span class="typing-dots" aria-hidden="true"><span>.</span><span>.</span><span>.</span></span> <span class="typing-label">${label}</span>`;
            el.classList.remove('visually-hidden');
        } else {
            this.clearTypingIndicator();
        }
    }
    
    clearTypingIndicator() {
        const el = document.getElementById('typing-indicator');
        if (el) {
            el.classList.add('visually-hidden');
            el.textContent = '';
        }
    }
    // Test method for typing indicator (can be called from console for debugging)
    testTypingIndicator() {
        console.log('Testing typing indicator...');
        
        // Test showing typing indicator
        this.setTypingIndicator(true, this.isDirector ? 'matcher' : 'director');
        console.log('Typing indicator should now be visible');
        
        // Test hiding typing indicator after 2 seconds
        setTimeout(() => {
            this.setTypingIndicator(false);
            console.log('Typing indicator should now be hidden');
        }, 2000);
        
        // Test sending typing status
        this.sendTyping(true);
        console.log('Typing status sent to server');
        
        // Test clearing typing status after 1 second
        setTimeout(() => {
            this.sendTyping(false);
            console.log('Typing status cleared');
        }, 1000);
    }

    // Setup basket refocus functionality
    setupBasketRefocus() {
        // Only for Matcher role (since Directors can't select baskets)
        if (this.isDirector) return;
        
        // Add event listeners to all basket-related elements
        document.addEventListener('click', (event) => {
            // Check if the clicked element is a basket or staging slot
            const isBasketClick = event.target.closest('.staging-slot, .target-slot, .basket-slot');
            
            if (isBasketClick) {
                // Refocus the chat input after a brief delay
                setTimeout(() => {
                    const chatInput = document.getElementById('chat-input');
                    if (chatInput) {
                        chatInput.focus();
                        console.log('🔍 Chat input refocused after basket interaction');
                    }
                }, 10);
            }
        });
        
        console.log('🎯 Basket refocus functionality initialized');
    }

    // ========================================
    // MAGNIFYING GLASS ZOOM FUNCTIONALITY
    // ========================================
    initializeMagnifier() {
        // Create the magnifier lens element
        this.magnifierLens = document.createElement('div');
        this.magnifierLens.className = 'magnifier-lens';
        document.body.appendChild(this.magnifierLens);
        
        // Magnifier configuration
        this.magnifierZoom = 1.005; // zoom level
        this.magnifierSize = 350; // lens diameter in pixels
        this.magnifierOffset = 20; // offset from cursor
        
        // Apply size to the lens element
        this.magnifierLens.style.width = `${this.magnifierSize}px`;
        this.magnifierLens.style.height = `${this.magnifierSize}px`;
        
        // Track current magnified image
        this.currentMagnifiedImg = null;
        
        // Bind event handlers
        this.handleMagnifierMouseMove = this.handleMagnifierMouseMove.bind(this);
        this.handleMagnifierMouseEnter = this.handleMagnifierMouseEnter.bind(this);
        this.handleMagnifierMouseLeave = this.handleMagnifierMouseLeave.bind(this);
        
        // Setup magnifier on all basket images (with delayed retries for dynamic content)
        this.setupMagnifierListeners();
        
        // Retry setup after delays to catch dynamically created content
        // The staging area is created by JavaScript which may run after this
        const retryDelays = [100, 300, 500, 1000, 2000];
        retryDelays.forEach(delay => {
            setTimeout(() => this.setupMagnifierListeners(), delay);
        });
        
        // Re-setup magnifier when staging area is dynamically created (for Matcher)
        if (!this.isDirector) {
            // Use MutationObserver to catch dynamically added basket images
            const observer = new MutationObserver((mutations) => {
                let shouldResetup = false;
                mutations.forEach((mutation) => {
                    if (mutation.addedNodes.length > 0) {
                        mutation.addedNodes.forEach((node) => {
                            if (node.nodeType === 1 && (
                                node.classList?.contains('staging-slot') ||
                                node.classList?.contains('basket-slot') ||
                                node.querySelector?.('.basket-image')
                            )) {
                                shouldResetup = true;
                            }
                        });
                    }
                });
                if (shouldResetup) {
                    // Debounce the re-setup
                    clearTimeout(this._magnifierSetupTimer);
                    this._magnifierSetupTimer = setTimeout(() => {
                        this.setupMagnifierListeners();
                    }, 50);
                }
            });
            
            const stagingArea = document.getElementById('staging-area');
            if (stagingArea) {
                observer.observe(stagingArea, { childList: true, subtree: true });
            }
            
            // Also observe target area for filled slots
            const targetArea = document.getElementById('target-area');
            if (targetArea) {
                observer.observe(targetArea, { childList: true, subtree: true });
            }
        }
        
        // console.log('🔍 Magnifier zoom initialized');
    }
    
    setupMagnifierListeners() {
        // Use event delegation on the document for better dynamic content support
        if (this._magnifierDelegationSetup) {
            // Already set up delegation, just log current image count
            const images = document.querySelectorAll('.basket-image');
            console.log(`🔍 Magnifier ready (${images.length} basket images found)`);
            return;
        }
        
        this._magnifierDelegationSetup = true;
        
        // Use event delegation - attach to document and check target
        document.addEventListener('mouseenter', (e) => {
            const img = e.target;
            if (img && img.tagName === 'IMG' && img.classList.contains('basket-image')) {
                this.handleMagnifierMouseEnter(e);
            }
        }, true); // Use capture phase
        
        document.addEventListener('mouseleave', (e) => {
            const img = e.target;
            if (img && img.tagName === 'IMG' && img.classList.contains('basket-image')) {
                this.handleMagnifierMouseLeave(e);
            }
        }, true); // Use capture phase
        
        document.addEventListener('mousemove', (e) => {
            // Only process if we're currently magnifying
            if (this.currentMagnifiedImg) {
                this.handleMagnifierMouseMove(e);
            }
        });
        
        const images = document.querySelectorAll('.basket-image');
        console.log(`🔍 Magnifier delegation setup complete (${images.length} basket images currently found)`);
    }
    
    handleMagnifierMouseEnter(event) {
        const img = event.target;
        if (!img || !img.src) {
            console.log('🔍 Magnifier: invalid img', img);
            return;
        }
        
        // console.log('🔍 Magnifier ENTER:', img.src.substring(img.src.lastIndexOf('/') + 1));
        
        this.currentMagnifiedImg = img;
        
        // Set the background image for the magnifier lens
        this.magnifierLens.style.backgroundImage = `url('${img.src}')`;
        
        // Calculate the background size preserving aspect ratio
        // Use natural dimensions if available, otherwise use displayed dimensions
        const naturalW = img.naturalWidth || img.width;
        const naturalH = img.naturalHeight || img.height;
        const aspectRatio = naturalW / naturalH;
        
        // Scale so the image fills the lens area while maintaining aspect ratio
        let bgWidth, bgHeight;
        if (aspectRatio >= 1) {
            // Wider than tall - fit height, let width extend
            bgHeight = this.magnifierSize * this.magnifierZoom;
            bgWidth = bgHeight * aspectRatio;
        } else {
            // Taller than wide - fit width, let height extend
            bgWidth = this.magnifierSize * this.magnifierZoom;
            bgHeight = bgWidth / aspectRatio;
        }
        
        this.magnifierLens.style.backgroundSize = `${bgWidth}px ${bgHeight}px`;
        
        // Store these for position calculations
        this._bgWidth = bgWidth;
        this._bgHeight = bgHeight;
        
        // Show the magnifier
        this.magnifierLens.classList.add('active');
        // console.log('🔍 Magnifier lens active:', this.magnifierLens.classList.contains('active'));
        
        // Position immediately
        this.updateMagnifierPosition(event);
    }
    
    handleMagnifierMouseLeave(event) {
        // console.log('🔍 Magnifier LEAVE');
        this.currentMagnifiedImg = null;
        this.magnifierLens.classList.remove('active');
    }
    
    handleMagnifierMouseMove(event) {
        if (!this.currentMagnifiedImg) return;
        this.updateMagnifierPosition(event);
    }
    
    updateMagnifierPosition(event) {
        const img = this.currentMagnifiedImg;
        if (!img) return;
        
        const imgRect = img.getBoundingClientRect();
        
        // Calculate mouse position relative to the image (0-1)
        const relX = (event.clientX - imgRect.left) / imgRect.width;
        const relY = (event.clientY - imgRect.top) / imgRect.height;
        
        // Clamp to image bounds
        const clampedX = Math.max(0, Math.min(1, relX));
        const clampedY = Math.max(0, Math.min(1, relY));
        
        // Use the aspect-ratio-aware background dimensions
        const bgWidth = this._bgWidth || (this.magnifierSize * this.magnifierZoom);
        const bgHeight = this._bgHeight || (this.magnifierSize * this.magnifierZoom);
        
        // Calculate background position to show zoomed area
        const bgX = -(clampedX * bgWidth - this.magnifierSize / 2);
        const bgY = -(clampedY * bgHeight - this.magnifierSize / 2);
        
        this.magnifierLens.style.backgroundPosition = `${bgX}px ${bgY}px`;
        
        // Position the lens near the cursor
        // Calculate optimal position to avoid going off-screen
        let lensX = event.clientX + this.magnifierOffset;
        let lensY = event.clientY - this.magnifierSize / 2;
        
        // Adjust if going off right edge
        if (lensX + this.magnifierSize > window.innerWidth - 10) {
            lensX = event.clientX - this.magnifierSize - this.magnifierOffset;
        }
        
        // Adjust if going off top or bottom
        if (lensY < 10) {
            lensY = 10;
        } else if (lensY + this.magnifierSize > window.innerHeight - 10) {
            lensY = window.innerHeight - this.magnifierSize - 10;
        }
        
        this.magnifierLens.style.left = `${lensX}px`;
        this.magnifierLens.style.top = `${lensY}px`;
    }
}
let draggableGrid = null;
function initializeDraggableGrid(config) {
    draggableGrid = new DraggableGrid(config);
    
    // Make typing indicator accessible globally for testing
    window.testTypingIndicator = () => {
        if (draggableGrid) {
            draggableGrid.testTypingIndicator();
        } else {
            console.warn('DraggableGrid not initialized yet');
        }
    };
    
    window.debugTypingIndicator = () => {
        if (draggableGrid) {
            draggableGrid.debugTypingIndicator();
        } else {
            console.warn('DraggableGrid not initialized yet');
        }
    };
}
function liveRecv(data) {
    if (draggableGrid) {
        draggableGrid.handleLiveUpdate(data);
    }
}

// Simple test function that can be called directly from console
window.simpleTypingTest = function() {
    console.log('Running simple typing indicator test...');
    
    // Check if typing indicator element exists
    const typingEl = document.getElementById('typing-indicator');
    if (!typingEl) {
        console.error('Typing indicator element not found! Make sure you are on the DraggableGrid page.');
        return;
    }
    
    console.log('✓ Typing indicator element found');
    
    // Test showing typing indicator
    typingEl.innerHTML = '<span class="typing-dots" aria-hidden="true"><span>.</span><span>.</span><span>.</span></span> <span class="typing-label">Director is typing…</span>';
    typingEl.classList.remove('visually-hidden');
    console.log('✓ Typing indicator should now be visible');
    
    // Test hiding after 3 seconds
    setTimeout(() => {
        typingEl.classList.add('visually-hidden');
        typingEl.textContent = '';
        console.log('✓ Typing indicator hidden');
    }, 3000);
    
    console.log('Test complete! Check the chat area for the typing indicator.');
};

// Test function to simulate receiving typing updates (for debugging)
window.testTypingCommunication = function() {
    console.log('🧪 Testing typing communication...');
    
    if (!window.draggableGrid) {
        console.error('❌ DraggableGrid not initialized yet');
        return;
    }
    
    // Simulate receiving a typing update from the server
    const mockTypingUpdate = {
        [window.js_vars.my_id]: {
            success: true,
            broadcast: true,
            partner_typing: true,
            partner_role: window.draggableGrid.isDirector ? 'matcher' : 'director'
        }
    };
    
    console.log('📥 Simulating typing update:', mockTypingUpdate);
    window.draggableGrid.handleLiveUpdate(mockTypingUpdate);
    
    // Hide after 3 seconds
    setTimeout(() => {
        const mockStopTyping = {
            [window.js_vars.my_id]: {
                success: true,
                broadcast: true,
                partner_typing: false,
                partner_role: window.draggableGrid.isDirector ? 'matcher' : 'director'
            }
        };
        console.log('📥 Simulating stop typing update:', mockStopTyping);
        window.draggableGrid.handleLiveUpdate(mockStopTyping);
    }, 3000);
    
    console.log('✅ Test complete! Check if typing indicator appeared and disappeared.');
};

// Test if the page is ready
window.checkPageReady = function() {
    console.log('Checking page readiness...');
    console.log('- DraggableGrid instance:', window.draggableGrid ? 'Available' : 'Not available');
    console.log('- Typing indicator element:', document.getElementById('typing-indicator') ? 'Found' : 'Not found');
    console.log('- Chat input element:', document.getElementById('chat-input') ? 'Found' : 'Not found');
    console.log('- Page URL:', window.location.href);
    
    if (window.draggableGrid) {
        console.log('- Player role:', window.draggableGrid.isDirector ? 'Director' : 'Matcher');
    }
};

// Version check function
window.checkDraggableGridVersion = function() {
    console.log('=== DraggableGrid Version Check ===');
    console.log('JavaScript file loaded successfully');
    console.log('Version: 2.3 - Magnifying glass zoom + typing indicator + sounds');
    console.log('Available test functions:');
    console.log('- simpleTypingTest() - Basic typing indicator test');
    console.log('- checkPageReady() - Check if page elements are ready');
    console.log('- testTypingIndicator() - Full typing indicator test');
    console.log('- debugTypingIndicator() - Debug info');
    console.log('- testSoundSystem() - Test sound notifications');
    console.log('- testMagnifier() - Check magnifier status');
    console.log('- setMagnifierZoom(n) - Set zoom level (1-10)');
    console.log('- setMagnifierSize(n) - Set lens size in pixels (50-400)');
    console.log('===============================');
};

// Auto-run version check when script loads
if (typeof window !== 'undefined') {
    window.checkDraggableGridVersion();
}

// Magnifier configuration functions
window.setMagnifierZoom = function(zoom) {
    if (!window.draggableGrid) {
        console.error('❌ DraggableGrid not initialized yet');
        return;
    }
    if (typeof zoom !== 'number' || zoom < 1 || zoom > 10) {
        console.error('❌ Zoom must be a number between 1 and 10');
        return;
    }
    window.draggableGrid.magnifierZoom = zoom;
    console.log(`🔍 Magnifier zoom set to ${zoom}x`);
};

window.setMagnifierSize = function(size) {
    if (!window.draggableGrid) {
        console.error('❌ DraggableGrid not initialized yet');
        return;
    }
    if (typeof size !== 'number' || size < 50 || size > 400) {
        console.error('❌ Size must be a number between 50 and 400');
        return;
    }
    const dg = window.draggableGrid;
    dg.magnifierSize = size;
    dg.magnifierLens.style.width = `${size}px`;
    dg.magnifierLens.style.height = `${size}px`;
    console.log(`🔍 Magnifier size set to ${size}px (refresh hover to see effect)`);
};

window.testMagnifier = function() {
    console.log('🔍 Magnifier Test Info:');
    if (!window.draggableGrid) {
        console.error('❌ DraggableGrid not initialized');
        return;
    }
    const dg = window.draggableGrid;
    console.log(`  - Zoom level: ${dg.magnifierZoom}x`);
    console.log(`  - Lens size: ${dg.magnifierSize}px`);
    console.log(`  - Lens element exists:`, !!dg.magnifierLens);
    console.log(`  - Lens in DOM:`, document.body.contains(dg.magnifierLens));
    console.log(`  - Delegation setup:`, !!dg._magnifierDelegationSetup);
    
    const images = document.querySelectorAll('.basket-image');
    console.log(`  - Basket images found: ${images.length}`);
    
    // Show the lens briefly for testing
    if (dg.magnifierLens && images.length > 0) {
        console.log('🔍 Testing magnifier on first image...');
        const testImg = images[0];
        dg.magnifierLens.style.backgroundImage = `url('${testImg.src}')`;
        const bgSize = dg.magnifierSize * dg.magnifierZoom;
        dg.magnifierLens.style.backgroundSize = `${bgSize}px ${bgSize}px`;
        dg.magnifierLens.style.backgroundPosition = 'center';
        dg.magnifierLens.style.left = '100px';
        dg.magnifierLens.style.top = '100px';
        dg.magnifierLens.classList.add('active');
        console.log('✅ Magnifier lens should be visible at top-left. Hiding in 3 seconds...');
        setTimeout(() => {
            dg.magnifierLens.classList.remove('active');
            console.log('🔍 Magnifier hidden');
        }, 3000);
    }
    
    console.log('');
    console.log('📝 Configuration commands:');
    console.log('  - setMagnifierZoom(2)  // Set zoom to 3x (1-10)');
    console.log('  - setMagnifierSize(400)  // Set lens size to 200px (50-400)');
};

    // Test function for sound system
    window.testSoundSystem = function() {
        console.log('🔊 Testing sound system...');
        
        if (!window.draggableGrid) {
            console.error('❌ DraggableGrid not initialized yet');
            return;
        }
        
        console.log('✅ Testing message sound...');
        window.draggableGrid.playMessageSound();
        
        setTimeout(() => {
            console.log('✅ Testing sound toggle...');
            const wasEnabled = window.draggableGrid.soundEnabled;
            window.draggableGrid.toggleSound();
            console.log(`Sound was ${wasEnabled ? 'enabled' : 'disabled'}, now ${window.draggableGrid.soundEnabled ? 'enabled' : 'disabled'}`);
            
            // Toggle back to original state
            setTimeout(() => {
                window.draggableGrid.toggleSound();
                console.log('Sound restored to original state');
            }, 1000);
        }, 1000);
        
        console.log('🔊 Sound test complete! Check console for results.');
    };