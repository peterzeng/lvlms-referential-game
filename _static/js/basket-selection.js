// BasketSelection JavaScript
// This file handles the interactive basket selection experiment

class BasketSelectionGame {
    constructor(config) {
        // Configuration from template
        this.isDirector = config.isDirector;
        this.selectedBaskets = config.selectedBaskets || [];
        this.targetBaskets = config.targetBaskets || [];
        this.chatMessages = config.chatMessages || [];
        this.partnerMessages = config.partnerMessages || [];
        
        // Initialize when page loads
        document.addEventListener('DOMContentLoaded', () => {
            this.initialize();
        });
    }
    
    initialize() {
        this.initializeChat();
        this.initializeBasketSelection();
        this.updateSelectionCount();
        this.setupLiveUpdates();
    }

    initializeBasketSelection() {
        if (!this.isDirector) {
            // Add click handlers for basket selection (Matcher only)
            document.querySelectorAll('.basket-wrapper').forEach(wrapper => {
                wrapper.addEventListener('click', () => {
                    const basketId = parseInt(wrapper.closest('.basket-slot').dataset.basketId);
                    this.toggleBasketSelection(basketId);
                });
            });

            // Clear all selections button
            const clearBtn = document.getElementById('clear-selections-btn');
            if (clearBtn) {
                clearBtn.addEventListener('click', () => {
                    this.clearAllSelections();
                });
            }
        }

        // Task complete button
        const completeBtn = document.getElementById('task-complete-btn');
        if (completeBtn) {
            completeBtn.addEventListener('click', () => {
                this.completeTask();
            });
        }
    }

    toggleBasketSelection(basketId) {
        if (this.isDirector) return; // Only Matcher can select

        console.log('toggleBasketSelection called for basket:', basketId); // Debug log

        liveSend({
            'select_basket': true,
            'basket_id': basketId,
            'action': 'toggle',
            'timestamp': new Date().toISOString()
        });
        
        // Refocus the chat input after basket selection
        this.refocusChatInput();
    }

    clearAllSelections() {
        if (this.isDirector) return;

        this.selectedBaskets.forEach(basketId => {
            liveSend({
                'select_basket': true,
                'basket_id': basketId,
                'action': 'deselect',
                'timestamp': new Date().toISOString()
            });
        });
        
        // Refocus the chat input after clearing selections
        this.refocusChatInput();
    }

    updateBasketDisplay() {
        document.querySelectorAll('.basket-wrapper').forEach(wrapper => {
            const basketId = parseInt(wrapper.closest('.basket-slot').dataset.basketId);
            const isSelected = this.selectedBaskets.includes(basketId);
            
            if (isSelected) {
                wrapper.classList.add('selected-basket');
            } else {
                wrapper.classList.remove('selected-basket');
            }
        });
    }

    updateSelectionCount() {
        const countElement = document.getElementById('selection-count');
        if (countElement) {
            const count = this.selectedBaskets.length;
            countElement.textContent = `${count} basket${count !== 1 ? 's' : ''} selected`;
        }
    }

    completeTask() {
        liveSend({
            'task_complete': true,
            'timestamp': new Date().toISOString()
        });
    }

    // Helper method to refocus the chat input
    refocusChatInput() {
        console.log('refocusChatInput called'); // Debug log
        const chatInput = document.getElementById('chat-input');
        console.log('Chat input element found:', chatInput); // Debug log
        if (chatInput) {
            // Use setTimeout to ensure the focus happens after the click event is fully processed
            setTimeout(() => {
                console.log('Attempting to focus chat input'); // Debug log
                chatInput.focus();
                console.log('Focus applied, active element:', document.activeElement); // Debug log
            }, 10);
        } else {
            console.log('Chat input element not found!'); // Debug log
        }
    }

    // Chat functionality
    initializeChat() {
        const chatInput = document.getElementById('chat-input');
        const sendButton = document.getElementById('send-message-btn');

        if (chatInput) {
            chatInput.addEventListener('keypress', (e) => {
                if (e.key === 'Enter') {
                    this.sendMessage();
                }
            });
        }

        if (sendButton) {
            sendButton.addEventListener('click', () => {
                this.sendMessage();
            });
        }

        // Load existing messages
        this.loadChatMessages();
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
            
            liveSend({
                'send_message': true,
                'message': message,
                'timestamp': new Date().toISOString()
            });
            input.value = '';
        }
    }

    loadChatMessages() {
        // Combine and sort messages from both players
        let allMessages = [...this.chatMessages, ...this.partnerMessages];
        
        // Sort by timestamp
        allMessages.sort((a, b) => new Date(a.timestamp) - new Date(b.timestamp));
        
        this.displayMessages(allMessages);
    }

    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    displayMessages(messages) {
        const container = document.getElementById('chat-messages');
        if (!container) return;
        
        container.innerHTML = '';
        
        messages.forEach(msg => {
            const messageDiv = document.createElement('div');
            messageDiv.className = `chat-message ${this.escapeHtml(msg.sender_role)}`;
            
            messageDiv.innerHTML = `
                <div class="chat-sender">${this.escapeHtml(msg.sender_role).charAt(0).toUpperCase() + this.escapeHtml(msg.sender_role).slice(1)}</div>
                <div class="chat-text">${this.escapeHtml(msg.text)}</div>
                <div class="chat-timestamp">${new Date(msg.timestamp).toLocaleTimeString()}</div>
            `;
            
            container.appendChild(messageDiv);
        });
        
        // Scroll to bottom
        container.scrollTop = container.scrollHeight;
    }

    showStatus(message, type = 'info') {
        const statusElement = document.getElementById('status-message');
        if (!statusElement) return;
        
        statusElement.textContent = message;
        statusElement.className = `ms-3 text-${type === 'success' ? 'success' : type === 'error' ? 'danger' : 'muted'}`;
        
        // Clear after 3 seconds
        setTimeout(() => {
            statusElement.textContent = '';
            statusElement.className = 'ms-3 text-muted';
        }, 3000);
    }

    // Live updates handling
    setupLiveUpdates() {
        // This will be handled by oTree's live system
        // Make sure liveRecv is available globally
        window.liveRecv = (data) => this.handleLiveUpdate(data);
    }

    handleLiveUpdate(data) {
        if (data.success === false) {
            this.showStatus(data.message || 'Error occurred', 'error');
            return;
        }

        if (data.selected_baskets !== undefined) {
            this.selectedBaskets = data.selected_baskets;
            this.updateBasketDisplay();
            this.updateSelectionCount();
            this.showStatus(data.message, 'success');
        }

        if (data.new_message) {
            // Add new message to chat
            const messages = [data.new_message];
            this.displayMessages([...document.querySelectorAll('.chat-message')].map(el => ({
                text: el.querySelector('.chat-text').textContent,
                timestamp: el.querySelector('.chat-timestamp').textContent,
                sender_role: el.classList.contains('director') ? 'director' : 'matcher'
            })).concat(messages));
        }

        if (data.player_completed) {
            this.showStatus(`${data.player_completed.charAt(0).toUpperCase() + data.player_completed.slice(1)} completed the task!`, 'success');
            
            if (data.accuracy !== null && data.accuracy !== undefined) {
                this.showStatus(`Task completed with ${data.accuracy.toFixed(1)}% accuracy!`, 'success');
            }
        }

        if (data.all_players_completed) {
            // Both players completed - proceed to next page
            setTimeout(() => {
                const nextBtn = document.querySelector('[name="_next"]');
                if (nextBtn) nextBtn.click();
            }, 2000);
        }
    }
}

// Global variable to store the game instance
let basketGame = null;

// Function to initialize the game with template data
function initializeBasketGame(config) {
    basketGame = new BasketSelectionGame(config);
}

// Make liveRecv globally available for oTree
function liveRecv(data) {
    if (basketGame) {
        basketGame.handleLiveUpdate(data);
    }
}