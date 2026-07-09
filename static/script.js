let currentChatId = null;
let inactivityTimer = null;
const INACTIVITY_LIMIT_MS = 10 * 60 * 1000;
let currentStreamController = null; // Control de abortado de streaming activo
let isStreaming = false;
let currentLoadingId = null;
let currentStreamId = null;
let userCancelled = false;
let currentPartialText = '';

// Inicializar
document.addEventListener('DOMContentLoaded', () => {
    loadChats();
    autoResizeTextarea();
    // Deshabilitado por requerimiento: notificaciones de aprendizaje
    // (backend tiene learning_queue desactivada)
    // Pre-cargar sonido de listo
    try {
        window.readyAudio = new Audio('/ReadySound');
        window.readyAudio.preload = 'auto';
        window.readyAudio.load();
    } catch (e) { /* noop */ }
    try {
        const mi = document.getElementById('messageInput');
        if (mi) {
            mi.addEventListener('input', resetInactivityTimer);
            mi.addEventListener('keydown', resetInactivityTimer);
        }
    } catch (e) { }
    // Capturar Enter a nivel global para evitar navegaciones
    window.addEventListener('keydown', (ev) => {
        try {
            if (ev.key === 'Enter' && !ev.shiftKey) {
                const ae = document.activeElement;
                if (ae && ae.id === 'messageInput') {
                    ev.preventDefault();
                    sendMessage();
                }
            }
        } catch (_) {}
    }, true);
    // Prevenir navegación hacia atrás que pueda cerrar la ventana actual
    try {
        history.pushState(null, '', location.href);
        window.addEventListener('popstate', function () {
            history.pushState(null, '', location.href);
        });
    } catch (_) {}
});

// Auto-resize del textarea
function autoResizeTextarea() {
    const textarea = document.getElementById('messageInput');
    textarea.addEventListener('input', () => {
        textarea.style.height = 'auto';
        textarea.style.height = textarea.scrollHeight + 'px';
    });
}

// Manejar Enter
function handleKeyPress(event) {
    if (event.key === 'Enter' && !event.shiftKey) {
        event.preventDefault();
        sendMessage();
    }
}

// Cambiar estado del botón Enviar <-> Stop
function setSendButtonState(state) {
    const btn = document.getElementById('sendButton');
    if (!btn) return;
    if (state === 'stop') {
        btn.disabled = false;
        btn.title = 'Detener generación';
        btn.onclick = cancelStreaming;
        btn.innerHTML = `
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <rect x="6" y="6" width="12" height="12"/>
            </svg>
        `;
    } else {
        btn.disabled = false;
        btn.title = 'Enviar';
        btn.onclick = sendMessage;
        btn.innerHTML = `
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M22 2L11 13M22 2l-7 20-4-9-9-4 20-7z"/>
            </svg>
        `;
    }
}

// Cancelar streaming actual desde el botón Stop
function cancelStreaming() {
    try {
        if (currentStreamId) {
            try { fetch(`/api/chat/cancel/${currentStreamId}`, { method: 'POST' }); } catch (e) {}
        }
        if (currentStreamController) {
            currentStreamController.abort();
        }
    } catch (e) {}
    isStreaming = false;
    userCancelled = true;
    if (currentLoadingId) {
        try {
            const loadingEl = document.getElementById(currentLoadingId);
            if (loadingEl) {
                const contentDiv = loadingEl.querySelector('.message-content');
                if (contentDiv) {
                    const text = currentPartialText && currentPartialText.trim() ? currentPartialText : 'Generación detenida por el usuario.';
                    contentDiv.innerHTML = formatMessage(text);
                }
            }
        } catch (e) {}
        currentLoadingId = null;
    } else {
        addMessageToUI('Generación detenida por el usuario.', 'assistant');
    }
    currentPartialText = '';
    try {
        const input = document.getElementById('messageInput');
        const sendButton = document.getElementById('sendButton');
        if (sendButton) sendButton.disabled = false;
        if (input) { input.disabled = false; input.focus(); }
        setSendButtonState('send');
    } catch (e) {}
    currentStreamId = null;
}

// Nuevo chat
function newChat() {
    // Forzar creación de nuevo chat al hacer clic en New Chat
    currentChatId = null;
    document.getElementById('messages').style.display = 'none';
    document.getElementById('welcomeScreen').style.display = 'flex';
    document.getElementById('messageInput').value = '';
    document.getElementById('messageInput').focus();
    
    // Remover clase active de todos los chats
    document.querySelectorAll('.chat-item').forEach(item => {
        item.classList.remove('active');
    });
    if (inactivityTimer) {
        clearTimeout(inactivityTimer);
        inactivityTimer = null;
    }
    try { hideStickyPrompt(); } catch (e) {}
}

// Cargar chats anteriores
async function loadChats() {
    try {
        const response = await fetch('/api/chats');
        const chats = await response.json();
        
        const historyDiv = document.getElementById('chatHistory');
        historyDiv.innerHTML = '';
        
        chats.forEach(chat => {
            const chatItem = document.createElement('div');
            chatItem.className = 'chat-item';
            
            // Texto del chat
            const chatText = document.createElement('span');
            chatText.className = 'chat-item-text';
            chatText.textContent = chat.title;
            chatText.onclick = () => loadChat(chat.id);
            // Permitir renombrar con doble click
            chatText.ondblclick = (e) => {
                e.stopPropagation();
                renameChat(chat.id, chat.title);
            };
            
            // Botón de renombrar
            const renameBtn = document.createElement('button');
            renameBtn.className = 'chat-rename-btn';
            renameBtn.innerHTML = `
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/>
                    <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/>
                </svg>
            `;
            renameBtn.onclick = (e) => {
                e.stopPropagation();
                renameChat(chat.id, chat.title);
            };
            
            // Botón de eliminar
            const deleteBtn = document.createElement('button');
            deleteBtn.className = 'chat-delete-btn';
            deleteBtn.innerHTML = `
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <path d="M3 6h18M19 6v14a2 2 0 01-2 2H7a2 2 0 01-2-2V6m3 0V4a2 2 0 012-2h4a2 2 0 012 2v2"/>
                </svg>
            `;
            deleteBtn.onclick = (e) => {
                e.stopPropagation();
                deleteChat(chat.id);
            };
            
            chatItem.appendChild(chatText);
            chatItem.appendChild(renameBtn);
            chatItem.appendChild(deleteBtn);
            historyDiv.appendChild(chatItem);
        });
    } catch (error) {
        console.error('Error cargando chats:', error);
    }
}

// Renombrar chat
async function renameChat(chatId, currentTitle) {
    const newTitle = prompt('Nuevo nombre para el chat:', currentTitle);
    if (!newTitle || newTitle.trim() === '' || newTitle === currentTitle) return;
    
    try {
        const response = await fetch(`/api/chats/${chatId}/rename`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ title: newTitle.trim() })
        });
        
        if (response.ok) {
            loadChats();
            showNotification('Chat renombrado', 'success');
        } else {
            showNotification('Error al renombrar', 'error');
        }
    } catch (error) {
        console.error('Error renombrando chat:', error);
        showNotification('Error de conexión', 'error');
    }
}

// Eliminar chat
async function deleteChat(chatId) {
    if (!confirm('¿Eliminar este chat?')) return;
    
    try {
        const response = await fetch(`/api/chats/${chatId}`, {
            method: 'DELETE'
        });
        
        if (response.ok) {
            // Si era el chat actual, volver a welcome
            if (currentChatId === chatId) {
                newChat();
            }
            // Recargar lista
            loadChats();
        }
    } catch (error) {
        console.error('Error eliminando chat:', error);
    }
}

// Cargar un chat específico
async function loadChat(chatId) {
    try {
        const response = await fetch(`/api/chats/${chatId}`);
        const chat = await response.json();
        
        currentChatId = chatId;
        
        // Ocultar welcome screen
        document.getElementById('welcomeScreen').style.display = 'none';
        
        // Mostrar mensajes
        const messagesDiv = document.getElementById('messages');
        messagesDiv.style.display = 'flex';
        messagesDiv.innerHTML = '';
        
        chat.messages.forEach(msg => {
            addMessageToUI(msg.content, msg.role);
        });
        try {
            let lastUser = null;
            for (let i = (chat.messages || []).length - 1; i >= 0; i--) {
                const m = chat.messages[i];
                if (m && m.role === 'user' && m.content) { lastUser = m.content; break; }
            }
            if (lastUser) updateStickyPrompt(lastUser); else hideStickyPrompt();
        } catch (e) {}
        
        // Marcar como activo
        document.querySelectorAll('.chat-item').forEach(item => {
            item.classList.remove('active');
        });
        
        // Encontrar y marcar el chat actual
        const allChats = document.querySelectorAll('.chat-item');
        allChats.forEach(item => {
            const textSpan = item.querySelector('.chat-item-text');
            if (textSpan && textSpan.textContent === chat.title) {
                item.classList.add('active');
            }
        });
        
        // Scroll al final
        scrollToBottom();
        resetInactivityTimer();
        
    } catch (error) {
        console.error('Error cargando chat:', error);
    }
}

// Enviar mensaje
async function sendMessage() {
    const input = document.getElementById('messageInput');
    const query = input.value.trim();
    
    if (!query) return;
    // Si hay un streaming activo, abortarlo antes de iniciar uno nuevo
    try { if (currentStreamController) { currentStreamController.abort(); } } catch (e) {}
    currentStreamController = new AbortController();
    isStreaming = true;
    userCancelled = false;
    currentPartialText = '';
    
    // Deshabilitar botón y input
    const sendButton = document.getElementById('sendButton');
    setSendButtonState('stop');
    input.disabled = true;
    
    // Ocultar welcome screen si está visible
    document.getElementById('welcomeScreen').style.display = 'none';
    
    // Mostrar área de mensajes
    const messagesDiv = document.getElementById('messages');
    messagesDiv.style.display = 'flex';
    
    // Agregar mensaje del usuario
    addMessageToUI(query, 'user');
    try { updateStickyPrompt(query); } catch (e) {}
    resetInactivityTimer();
    
    // Limpiar input
    input.value = '';
    input.style.height = 'auto';
    
    // Hacer scroll para anclar el mensaje del usuario arriba
    setTimeout(() => {
        scrollToAnchorUserMessage();
    }, 100);
    
    // Agregar mensaje de loading del asistente
    const loadingId = addLoadingMessage();
    currentLoadingId = loadingId;
    
    try {
        const payload = {
            query: query,
            chat_id: (currentChatId || null),
            length_mode: (document.getElementById('noContextToggle')?.checked ? 'long' : (document.getElementById('lengthModeSelect')?.value || 'short')),
            no_context: !!document.getElementById('noContextToggle')?.checked
        };
        const response = await fetch('/api/chat/stream', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
            signal: currentStreamController.signal
        });
        if (!response.ok) {
            let message = 'No se pudo obtener respuesta del servidor.';
            try {
                const errData = await response.json();
                if (errData && errData.error) message = errData.error;
            } catch (e) { }
            removeLoadingMessage(loadingId);
            currentLoadingId = null;
            addMessageToUI('Error: ' + message, 'assistant');
            return;
        }

        let loadingEl = document.getElementById(loadingId);
        let contentDiv = loadingEl ? loadingEl.querySelector('.message-content') : null;
        if (contentDiv) contentDiv.innerHTML = '';

        let streamedText = '';
        let finalData = null;
        let readingTimer = null;
        let readingIndex = 0;
        let readingMessages = [];
        let firstToken = false;

        const reader = response.body && response.body.getReader ? response.body.getReader() : null;
        if (reader) {
            const decoder = new TextDecoder();
            let buffer = '';
            while (true) {
                const { value, done } = await reader.read();
                if (done) break;
                buffer += decoder.decode(value, { stream: true });
                const lines = buffer.split('\n');
                buffer = lines.pop();
                for (const line of lines) {
                    const t = line.trim();
                    if (!t) continue;
                    let obj = null;
                    try { obj = JSON.parse(t); } catch (e) { continue; }
                    if (obj.event === 'start' && obj.stream_id) {
                        currentStreamId = obj.stream_id;
                        continue;
                    }
                    if (obj.event === 'token' && obj.token) {
                        if (!firstToken) {
                            firstToken = true;
                            if (readingTimer) { clearInterval(readingTimer); readingTimer = null; }
                        }
                        streamedText += obj.token;
                        currentPartialText = streamedText;
                        if (contentDiv) contentDiv.innerHTML = formatMessage(streamedText);
                        scrollToBottom();
                    } else if (obj.event === 'done') {
                        finalData = obj;
                    } else if (obj.event === 'docs' && Array.isArray(obj.docs)) {
                        if (!firstToken && contentDiv && !readingTimer) {
                            readingMessages = (obj.docs || []).map((d, i) => {
                                const nm = (d && d.name) ? String(d.name) : 'Documento';
                                const label = /anexo/i.test(nm) ? `Leyendo ${nm} ...` : `Interpretando ${nm} ...`;
                                return label;
                            });
                            if (readingMessages.length === 0) readingMessages = ['Buscando documentos ...'];
                            readingIndex = 0;
                            const renderHint = () => {
                                if (!firstToken && contentDiv) {
                                    const msg = readingMessages[readingIndex % readingMessages.length];
                                    contentDiv.innerHTML = `<div class="reading-hints">${msg}</div>`;
                                    readingIndex = (readingIndex + 1) % readingMessages.length;
                                }
                            };
                            renderHint();
                            readingTimer = setInterval(renderHint, 3500);
                        }
                    } else if (obj.event === 'error') {
                        removeLoadingMessage(loadingId);
                        currentLoadingId = null;
                        addMessageToUI('Error: ' + (obj.message || 'Error de streaming'), 'assistant');
                        return;
                    }
                }
            }
        }

        if (readingTimer) { try { clearInterval(readingTimer); } catch (e) {} readingTimer = null; }
        removeLoadingMessage(loadingId);
        currentLoadingId = null;
        if (finalData) {
            addMessageToUI(finalData.response || streamedText || 'Sin respuesta', 'assistant', finalData.sources || [], { latency_s: finalData.latency_s });
            currentChatId = finalData.chat_id || currentChatId;
            // Recargar lista y enfocar el chat creado/actualizado
            try {
                await loadChats();
                if (currentChatId) { await loadChat(currentChatId); }
            } catch (e) { try { loadChats(); } catch (e2) {} }
            resetInactivityTimer();
            playReadySound();
        } else {
            let data = null;
            try { data = await response.json(); } catch (e) {}
            if (data && data.error && !data.response) {
                addMessageToUI('Error: ' + data.error, 'assistant');
            } else {
                addMessageToUI((data && data.response) || streamedText || 'Sin respuesta', 'assistant', (data && data.sources) || [], { latency_s: data && data.latency_s, latency_ms: data && data.latency_ms, length_mode: data && data.length_mode });
                currentChatId = (data && data.chat_id) || currentChatId;
                try {
                    await loadChats();
                    if (currentChatId) { await loadChat(currentChatId); }
                } catch (e) { try { loadChats(); } catch (e2) {} }
                resetInactivityTimer();
                playReadySound();
            }
        }
        currentPartialText = '';
        
    } catch (error) {
        console.error('Error:', error);
        if (!userCancelled) {
            try { removeLoadingMessage(loadingId); } catch (e) {}
            currentLoadingId = null;
        }
        const errText = String(error && (error.name || error.message || error)) || '';
        const isAbort = userCancelled || /AbortError/i.test(errText) || /aborted/i.test(errText) || /abort/i.test(errText);
        if (!isAbort) {
            addMessageToUI('Error: No se pudo obtener respuesta del servidor.', 'assistant');
        }
    } finally {
        // Limpiar controlador de streaming
        currentStreamController = null;
        isStreaming = false;
        currentStreamId = null;
        // Restaurar botón Enviar e input
        setSendButtonState('send');
        // Rehabilitar botón y input
        sendButton.disabled = false;
        input.disabled = false;
        input.focus();
    }
    
    scrollToBottom();
}

// Reproducir sonido cuando la respuesta está lista
function playReadySound() {
    try {
        if (window.readyAudio) {
            window.readyAudio.currentTime = 0;
            window.readyAudio.play().catch(() => {});
        }
    } catch (e) { /* noop */ }
}

// Agregar mensaje al UI
function addMessageToUI(content, role, sources = null, meta = null) {
    const messagesDiv = document.getElementById('messages');
    
    const messageDiv = document.createElement('div');
    messageDiv.className = `message ${role}`;
    
    const avatar = document.createElement('div');
    avatar.className = 'message-avatar';
    avatar.textContent = role === 'user' ? 'U' : 'A';
    
    const contentDiv = document.createElement('div');
    contentDiv.className = 'message-content';
    
    // Formatear contenido (markdown simple)
    contentDiv.innerHTML = formatMessage(content);
    
    // Agregar fuentes si existen (colapsadas por defecto con toggle)
    if (sources && sources.length > 0) {
        const container = document.createElement('div');
        container.className = 'message-sources';
        container.style.marginTop = '8px';

        const header = document.createElement('div');
        header.className = 'sources-title';
        header.textContent = '📄 Fuentes';
        header.style.display = 'flex';
        header.style.alignItems = 'center';
        header.style.gap = '8px';

        const toggleBtn = document.createElement('button');
        toggleBtn.textContent = 'Ver fuentes';
        toggleBtn.style.cssText = 'margin-left:auto; background:#2b2b2b; color:#e5e7eb; border:1px solid #3f3f46; border-radius:6px; padding:4px 8px; font-size:12px; cursor:pointer;';

        const list = document.createElement('div');
        list.className = 'sources-list';
        list.style.display = 'none';
        list.style.marginTop = '6px';

        toggleBtn.addEventListener('click', () => {
            const isHidden = list.style.display === 'none';
            list.style.display = isHidden ? 'block' : 'none';
            toggleBtn.textContent = isHidden ? 'Ocultar fuentes' : 'Ver fuentes';
        });

        sources.forEach((source, index) => {
            const sourceItem = document.createElement('div');
            sourceItem.className = 'source-item';
            sourceItem.style.display = 'flex';
            sourceItem.style.alignItems = 'center';
            sourceItem.style.gap = '8px';
            sourceItem.style.margin = '4px 0';
            sourceItem.innerHTML = `
                <span class="source-number">${index + 1}.</span>
                <a href="#" class="source-link" onclick="openPDF('${source.name}', ${source.page}); return false;">
                    ${source.name} - Página ${source.page}
                </a>
                <span class="source-score" title="Relevancia">${(source.score * 100).toFixed(0)}%</span>
            `;
            list.appendChild(sourceItem);
        });

        header.appendChild(toggleBtn);
        container.appendChild(header);
        container.appendChild(list);
        contentDiv.appendChild(container);
    }
    
    // Agregar meta (latencia)
    if (meta && (meta.latency_s || meta.latency_ms)) {
        const metaDiv = document.createElement('div');
        metaDiv.className = 'message-meta';
        const secs = (typeof meta.latency_s === 'number') ? meta.latency_s.toFixed(1) : (meta.latency_ms ? (meta.latency_ms/1000).toFixed(1) : null);
        if (secs) {
            metaDiv.textContent = `⏱ ${secs}s`;
            metaDiv.style.cssText = 'margin-top: 6px; font-size: 12px; color: #9aa0a6;';
            contentDiv.appendChild(metaDiv);
        }
    }
    
    messageDiv.appendChild(avatar);
    messageDiv.appendChild(contentDiv);
    messagesDiv.appendChild(messageDiv);
    
    scrollToBottom();
}

// Agregar mensaje de loading
function addLoadingMessage() {
    const messagesDiv = document.getElementById('messages');
    const loadingId = 'loading-' + Date.now();
    
    const messageDiv = document.createElement('div');
    messageDiv.className = 'message assistant';
    messageDiv.id = loadingId;
    
    const avatar = document.createElement('div');
    avatar.className = 'message-avatar';
    avatar.textContent = 'A';
    
    const contentDiv = document.createElement('div');
    contentDiv.className = 'message-content';
    contentDiv.innerHTML = '<div class="loading"><span></span><span></span><span></span></div>';
    
    messageDiv.appendChild(avatar);
    messageDiv.appendChild(contentDiv);
    messagesDiv.appendChild(messageDiv);
    
    scrollToBottom();
    
    return loadingId;
}

// Remover mensaje de loading
function removeLoadingMessage(loadingId) {
    const loadingMsg = document.getElementById(loadingId);
    if (loadingMsg) {
        loadingMsg.remove();
    }
}

// Formatear mensaje (markdown simple)
function formatMessage(text) {
    // Escapar HTML
    text = text.replace(/&/g, '&amp;')
               .replace(/</g, '&lt;')
               .replace(/>/g, '&gt;');
    
    // Negrita
    text = text.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
    
    // Código inline
    text = text.replace(/`([^`]+)`/g, '<code>$1</code>');
    
    // Bloques de código
    text = text.replace(/```([\s\S]*?)```/g, '<pre><code>$1</code></pre>');
    
    // Listas (mejorado para no capturar todo el contenido)
    // Convertir líneas con - o * en <li>
    text = text.replace(/^\s*[\-\*\+]\s+(.+)$/gm, '<li>$1</li>');
    
    // Envolver grupos consecutivos de <li> en <ul>
    // Usar regex no-greedy para evitar capturar todo
    text = text.replace(/(<li>.*?<\/li>(?:\s*<li>.*?<\/li>)*)/g, '<ul>$1</ul>');
    
    // Saltos de línea
    text = text.replace(/\n/g, '<br>');
    
    return text;
}

// Abrir PDF en página específica
async function openPDF(pdfName, page) {
    try {
        const response = await fetch('/api/open-pdf', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                pdf_name: pdfName,
                page: page
            })
        });
        
        const data = await response.json();
        
        if (data.success) {
            showNotification(data.message, 'success');
        } else {
            showNotification(data.error || 'Error abriendo PDF', 'error');
        }
    } catch (error) {
        console.error('Error abriendo PDF:', error);
        showNotification('Error de conexión', 'error');
    }
}

// Mostrar notificación temporal
function showNotification(message, type = 'info') {
    const notification = document.createElement('div');
    notification.className = `notification ${type}`;
    notification.textContent = message;
    notification.style.cssText = `
        position: fixed;
        top: 20px;
        right: 20px;
        padding: 15px 20px;
        background: ${type === 'success' ? '#10a37f' : type === 'error' ? '#ef4444' : '#3b82f6'};
        color: white;
        border-radius: 8px;
        box-shadow: 0 4px 12px rgba(0,0,0,0.15);
        z-index: 10000;
        animation: slideIn 0.3s ease;
    `;
    
    document.body.appendChild(notification);
    
    setTimeout(() => {
        notification.style.animation = 'slideOut 0.3s ease';
        setTimeout(() => notification.remove(), 300);
    }, 3000);
}

// Scroll al fondo
function scrollToBottom() {
    const container = document.getElementById('chatContainer');
    if (container && container.scrollHeight !== undefined) {
        container.scrollTop = container.scrollHeight;
    } else {
        const fallback = document.getElementById('messages');
        if (fallback) fallback.scrollTop = fallback.scrollHeight;
    }
}

// Scroll para anclar el último mensaje del usuario arriba
function scrollToAnchorUserMessage() {
    try {
        const messagesDiv = document.getElementById('messages');
        const userMessages = messagesDiv ? messagesDiv.querySelectorAll('.message.user') : [];
        if (userMessages.length > 0) {
            const lastUserMsg = userMessages[userMessages.length - 1];
            // Scroll para que el mensaje del usuario quede arriba
            const offsetTop = lastUserMsg.offsetTop - 20; // 20px de margen
            const container = document.getElementById('chatContainer');
            if (container) {
                container.scrollTop = offsetTop;
            } else if (messagesDiv) {
                messagesDiv.scrollTop = offsetTop;
            }
        }
    } catch (e) {
        console.error('Error en scrollToAnchorUserMessage:', e);
    }
}

function updateStickyPrompt(text) {
    try {
        const sp = document.getElementById('stickyPrompt');
        const spt = document.getElementById('stickyPromptText');
        if (sp && spt) {
            spt.textContent = text || '';
            sp.style.display = text ? 'block' : 'none';
        }
    } catch (e) { }
}

function hideStickyPrompt() {
    try {
        const sp = document.getElementById('stickyPrompt');
        const spt = document.getElementById('stickyPromptText');
        if (sp && spt) {
            spt.textContent = '';
            sp.style.display = 'none';
        }
    } catch (e) { }
}

function resetInactivityTimer() {
    try {
        if (inactivityTimer) {
            clearTimeout(inactivityTimer);
            inactivityTimer = null;
        }
        inactivityTimer = setTimeout(handleInactivityTimeout, INACTIVITY_LIMIT_MS);
    } catch (e) { }
}

function handleInactivityTimeout() {
    try {
        if (!currentChatId) {
            return;
        }
        showNotification('Chat reiniciado por inactividad (10 min)', 'info');
        newChat();
    } catch (e) { }
}

// Toggle help modal
function toggleHelp() {
    const modal = document.getElementById('helpModal');
    if (modal.style.display === 'none') {
        modal.style.display = 'flex';
    } else {
        modal.style.display = 'none';
    }
}

// Cerrar modal al hacer click fuera
document.addEventListener('click', (e) => {
    const modal = document.getElementById('helpModal');
    if (e.target === modal) {
        modal.style.display = 'none';
    }
});

// Toggle settings
function toggleSettings() {
    const options = [
        'Cerrar Servidor'
    ];
    
    const choice = confirm('¿Deseas cerrar el servidor?\n\nEsto detendrá el sistema completamente.\nPresiona OK para confirmar.');
    
    if (choice) {
        shutdownServer();
    }
}

// Cerrar servidor
async function shutdownServer() {
    try {
        const response = await fetch('/api/shutdown', {
            method: 'POST'
        });
        
        if (response.ok) {
            document.body.innerHTML = `
                <div style="display: flex; align-items: center; justify-content: center; height: 100vh; background: #1a1a1a; color: #ececec; flex-direction: column; gap: 20px;">
                    <h1>✓ Servidor Cerrado</h1>
                    <p>Puedes cerrar esta ventana</p>
                </div>
            `;
        }
    } catch (error) {
        console.log('Servidor cerrado');
        document.body.innerHTML = `
            <div style="display: flex; align-items: center; justify-content: center; height: 100vh; background: #1a1a1a; color: #ececec; flex-direction: column; gap: 20px;">
                <h1>✓ Servidor Cerrado</h1>
                <p>Puedes cerrar esta ventana</p>
            </div>
        `;
    }
}

// ========== LEARNING NOTIFICATION SYSTEM ==========
function startLearningNotificationPolling() {
    // Consultar cada 30 segundos (reducir carga)
    setInterval(async () => {
        try {
            const response = await fetch('/api/learning-notification');
            const notification = await response.json();
            
            updateLearningIndicator(notification);
        } catch (error) {
            console.error('Error obteniendo notificación de aprendizaje:', error);
        }
    }, 30000);  // 30 segundos
}

function updateLearningIndicator(notification) {
    const indicator = document.getElementById('learningIndicator');
    const spinner = indicator.querySelector('.spinner');
    const checkIcon = indicator.querySelector('.check-icon');
    const xIcon = indicator.querySelector('.x-icon');
    
    if (notification.status === 'none') {
        // No hay notificación - ocultar indicador
        indicator.style.display = 'none';
        return;
    }
    
    // Mostrar indicador
    indicator.style.display = 'block';
    
    // Ocultar todos los iconos primero
    spinner.style.display = 'none';
    checkIcon.style.display = 'none';
    xIcon.style.display = 'none';
    
    if (notification.status === 'learning') {
        // Mostrar spinner (aprendiendo)
        spinner.style.display = 'block';
    } else if (notification.status === 'approved') {
        // Mostrar check (aprobado)
        checkIcon.style.display = 'block';
        
        // Ocultar después de 3 segundos
        setTimeout(() => {
            indicator.style.display = 'none';
        }, 3000);
    } else if (notification.status === 'rejected') {
        // Mostrar X (rechazado)
        xIcon.style.display = 'block';
        
        // Ocultar después de 3 segundos
        setTimeout(() => {
            indicator.style.display = 'none';
        }, 3000);
    }
}
