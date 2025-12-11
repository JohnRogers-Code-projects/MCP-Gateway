/**
 * MCP Demo Dashboard - Interactive functionality
 * Uses Alpine.js for reactivity, vanilla JS for WebSocket handling
 */

// Wait for Alpine to be available
document.addEventListener('alpine:init', () => {

    // Main dashboard state
    Alpine.data('dashboard', () => ({
        activeTab: 'demo',

        // Demo/Tester state
        selectedMethod: 'tools/list',
        requestParams: '{}',
        response: null,
        responseTime: null,
        isLoading: false,
        error: null,

        // Test runner state
        testOutput: '',
        testsRunning: false,
        testSocket: null,

        // Example requests for quick testing
        examples: [
            {
                name: 'List Available Tools',
                method: 'tools/list',
                params: '{}',
                description: 'Discover all MCP tools exposed by the adapter'
            },
            {
                name: 'Get All Posts',
                method: 'tools/call',
                params: JSON.stringify({
                    name: 'get_posts',
                    arguments: {}
                }, null, 2),
                description: 'Fetch posts from JSONPlaceholder via MCP'
            },
            {
                name: 'Get Single Post',
                method: 'tools/call',
                params: JSON.stringify({
                    name: 'get_post',
                    arguments: { id: 1 }
                }, null, 2),
                description: 'Fetch a specific post by ID'
            },
            {
                name: 'Get Post Comments',
                method: 'tools/call',
                params: JSON.stringify({
                    name: 'get_post_comments',
                    arguments: { postId: 1 }
                }, null, 2),
                description: 'Fetch comments for a specific post'
            },
            {
                name: 'Create New Post',
                method: 'tools/call',
                params: JSON.stringify({
                    name: 'create_post',
                    arguments: {
                        title: 'MCP Demo Post',
                        body: 'Created via MCP protocol translation',
                        userId: 1
                    }
                }, null, 2),
                description: 'Create a post (simulated by JSONPlaceholder)'
            },
            {
                name: 'Get User Profile',
                method: 'tools/call',
                params: JSON.stringify({
                    name: 'get_user',
                    arguments: { id: 1 }
                }, null, 2),
                description: 'Fetch user details by ID'
            }
        ],

        // Load an example into the request form
        loadExample(example) {
            this.selectedMethod = example.method;
            this.requestParams = example.params;
            this.response = null;
            this.error = null;
        },

        // Build JSON-RPC request envelope
        buildRequest() {
            let params;
            try {
                params = JSON.parse(this.requestParams);
            } catch (e) {
                throw new Error(`Invalid JSON in params: ${e.message}`);
            }

            return {
                jsonrpc: '2.0',
                id: Date.now(),
                method: this.selectedMethod,
                params: params
            };
        },

        // Send MCP request to backend
        async sendRequest() {
            this.isLoading = true;
            this.error = null;
            this.response = null;

            const startTime = performance.now();

            try {
                const request = this.buildRequest();

                const res = await fetch('/mcp', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(request)
                });

                const data = await res.json();
                this.responseTime = Math.round(performance.now() - startTime);

                if (data.error) {
                    this.error = data.error;
                } else {
                    this.response = data;
                }
            } catch (e) {
                this.error = { message: e.message };
            } finally {
                this.isLoading = false;
            }
        },

        // Format JSON for display
        formatJson(obj) {
            if (!obj) return '';
            return JSON.stringify(obj, null, 2);
        },

        // Run tests via WebSocket for streaming output
        runTests() {
            if (this.testsRunning) return;

            this.testsRunning = true;
            this.testOutput = 'Connecting to test runner...\n';

            // Determine WebSocket URL based on current location
            const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
            const wsUrl = `${wsProtocol}//${window.location.host}/ws/tests`;

            this.testSocket = new WebSocket(wsUrl);

            this.testSocket.onopen = () => {
                this.testOutput = 'Running tests...\n\n';
            };

            this.testSocket.onmessage = (event) => {
                // Colorize output
                let line = event.data;
                if (line.includes('PASSED')) {
                    line = `<span class="pass">${this.escapeHtml(line)}</span>`;
                } else if (line.includes('FAILED')) {
                    line = `<span class="fail">${this.escapeHtml(line)}</span>`;
                } else if (line.includes('SKIPPED') || line.includes('skipped')) {
                    line = `<span class="skip">${this.escapeHtml(line)}</span>`;
                } else {
                    line = this.escapeHtml(line);
                }
                this.testOutput += line + '\n';

                // Auto-scroll
                this.$nextTick(() => {
                    const output = document.getElementById('test-output');
                    if (output) output.scrollTop = output.scrollHeight;
                });
            };

            this.testSocket.onclose = () => {
                this.testsRunning = false;
                this.testOutput += '\n--- Test run complete ---\n';
            };

            this.testSocket.onerror = (error) => {
                this.testsRunning = false;
                this.testOutput += `\nError: WebSocket connection failed. Make sure the server is running.\n`;
            };
        },

        escapeHtml(text) {
            const div = document.createElement('div');
            div.textContent = text;
            return div.innerHTML;
        },

        // Cleanup on page unload
        init() {
            window.addEventListener('beforeunload', () => {
                if (this.testSocket) {
                    this.testSocket.close();
                }
            });
        }
    }));
});
