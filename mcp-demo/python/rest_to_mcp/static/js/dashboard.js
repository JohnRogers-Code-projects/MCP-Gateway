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

        // Benchmark state
        benchmarkPayload: 'simple',
        benchmarkIterations: '10000',
        benchmarkRunning: false,
        benchmarkResults: [],
        benchmarkStatus: '',
        benchmarkComplete: false,
        rustAvailable: true,
        speedupFactor: null,
        benchmarkSocket: null,
        opsChart: null,
        latencyChart: null,

        // Playground state
        playgroundInput: '',
        playgroundRunning: false,
        playgroundSteps: [],
        playgroundScenario: null,
        playgroundComplete: false,
        playgroundError: null,
        playgroundSummary: null,
        playgroundSocket: null,
        playgroundExamples: [
            "Check weather for user 3",
            "Get all posts by user 1",
            "Show post 5 with comments",
            "List available tools",
            "Get weather for user 999"
        ],

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

        // Format number with commas
        formatNumber(n) {
            return new Intl.NumberFormat().format(Math.round(n));
        },

        // Truncate large results for display
        truncateResult(result) {
            const str = JSON.stringify(result, null, 2);
            if (str.length > 500) {
                return str.substring(0, 500) + '\n... (truncated)';
            }
            return str;
        },

        // ==================== BENCHMARK METHODS ====================

        runBenchmark() {
            if (this.benchmarkRunning) return;

            this.benchmarkRunning = true;
            this.benchmarkResults = [];
            this.benchmarkStatus = 'Connecting...';
            this.benchmarkComplete = false;
            this.speedupFactor = null;

            // Destroy existing charts
            if (this.opsChart) {
                this.opsChart.destroy();
                this.opsChart = null;
            }
            if (this.latencyChart) {
                this.latencyChart.destroy();
                this.latencyChart = null;
            }

            const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
            const wsUrl = `${wsProtocol}//${window.location.host}/ws/benchmarks`;

            this.benchmarkSocket = new WebSocket(wsUrl);

            this.benchmarkSocket.onopen = () => {
                this.benchmarkSocket.send(JSON.stringify({
                    payload: this.benchmarkPayload,
                    iterations: parseInt(this.benchmarkIterations)
                }));
            };

            this.benchmarkSocket.onmessage = (event) => {
                const data = JSON.parse(event.data);

                switch (data.type) {
                    case 'status':
                        this.benchmarkStatus = data.message;
                        this.rustAvailable = data.rust_available;
                        break;

                    case 'progress':
                        this.benchmarkStatus = data.message;
                        break;

                    case 'result':
                        this.benchmarkResults.push(data.result);
                        break;

                    case 'complete':
                        this.benchmarkComplete = true;
                        this.benchmarkRunning = false;
                        this.benchmarkStatus = '';
                        this.speedupFactor = data.speedup;
                        this.$nextTick(() => this.renderBenchmarkCharts());
                        break;

                    case 'error':
                        this.benchmarkStatus = `Error: ${data.message}`;
                        this.benchmarkRunning = false;
                        break;
                }
            };

            this.benchmarkSocket.onerror = () => {
                this.benchmarkStatus = 'WebSocket connection failed';
                this.benchmarkRunning = false;
            };

            this.benchmarkSocket.onclose = () => {
                if (this.benchmarkRunning) {
                    this.benchmarkRunning = false;
                }
            };
        },

        renderBenchmarkCharts() {
            if (this.benchmarkResults.length === 0) return;

            const colors = {
                python: '#f85149',
                rust: '#3fb950'
            };

            // Ops/sec bar chart
            const opsCtx = document.getElementById('opsChart');
            if (opsCtx) {
                this.opsChart = new Chart(opsCtx.getContext('2d'), {
                    type: 'bar',
                    data: {
                        labels: this.benchmarkResults.map(r => r.parser.charAt(0).toUpperCase() + r.parser.slice(1)),
                        datasets: [{
                            label: 'Operations/sec',
                            data: this.benchmarkResults.map(r => r.ops_per_sec),
                            backgroundColor: this.benchmarkResults.map(r => colors[r.parser] || '#888'),
                            borderRadius: 4
                        }]
                    },
                    options: {
                        responsive: true,
                        plugins: {
                            legend: { display: false },
                            tooltip: {
                                callbacks: {
                                    label: (ctx) => `${this.formatNumber(ctx.raw)} ops/sec`
                                }
                            }
                        },
                        scales: {
                            y: {
                                beginAtZero: true,
                                ticks: {
                                    callback: (value) => this.formatNumber(value)
                                }
                            }
                        }
                    }
                });
            }

            // Latency distribution chart
            const latencyCtx = document.getElementById('latencyChart');
            if (latencyCtx) {
                this.latencyChart = new Chart(latencyCtx.getContext('2d'), {
                    type: 'bar',
                    data: {
                        labels: ['P50', 'P95', 'P99'],
                        datasets: this.benchmarkResults.map(r => ({
                            label: r.parser.charAt(0).toUpperCase() + r.parser.slice(1),
                            data: [r.p50_ns, r.p95_ns, r.p99_ns],
                            backgroundColor: colors[r.parser] || '#888',
                            borderRadius: 4
                        }))
                    },
                    options: {
                        responsive: true,
                        plugins: {
                            legend: { position: 'top' },
                            tooltip: {
                                callbacks: {
                                    label: (ctx) => `${ctx.dataset.label}: ${this.formatNumber(ctx.raw)} ns`
                                }
                            }
                        },
                        scales: {
                            y: {
                                beginAtZero: true,
                                ticks: {
                                    callback: (value) => this.formatNumber(value)
                                }
                            }
                        }
                    }
                });
            }
        },

        // ==================== PLAYGROUND METHODS ====================

        runPlayground() {
            if (this.playgroundRunning || !this.playgroundInput.trim()) return;

            this.playgroundRunning = true;
            this.playgroundSteps = [];
            this.playgroundScenario = null;
            this.playgroundComplete = false;
            this.playgroundError = null;
            this.playgroundSummary = null;

            const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
            const wsUrl = `${wsProtocol}//${window.location.host}/ws/playground`;

            this.playgroundSocket = new WebSocket(wsUrl);

            this.playgroundSocket.onopen = () => {
                this.playgroundSocket.send(JSON.stringify({
                    input: this.playgroundInput
                }));
            };

            this.playgroundSocket.onmessage = (event) => {
                const data = JSON.parse(event.data);

                switch (data.type) {
                    case 'scenario_matched':
                        this.playgroundScenario = data.name;
                        // Pre-populate steps as pending
                        for (let i = 0; i < data.steps_count; i++) {
                            this.playgroundSteps.push({
                                tool: '...',
                                label: 'Pending...',
                                active: false,
                                complete: false,
                                args: null,
                                result: null
                            });
                        }
                        break;

                    case 'step_start':
                        if (this.playgroundSteps[data.index]) {
                            this.playgroundSteps[data.index] = {
                                ...this.playgroundSteps[data.index],
                                tool: data.tool,
                                label: data.label,
                                active: true,
                                complete: false
                            };
                        }
                        break;

                    case 'step_result':
                        if (this.playgroundSteps[data.index]) {
                            this.playgroundSteps[data.index] = {
                                ...this.playgroundSteps[data.index],
                                args: data.args,
                                result: data.result,
                                active: false,
                                complete: true
                            };
                        }
                        break;

                    case 'complete':
                        this.playgroundComplete = true;
                        this.playgroundRunning = false;
                        this.playgroundSummary = data.summary;
                        break;

                    case 'error':
                        this.playgroundError = data.message;
                        this.playgroundRunning = false;
                        break;
                }
            };

            this.playgroundSocket.onerror = () => {
                this.playgroundError = 'WebSocket connection failed';
                this.playgroundRunning = false;
            };

            this.playgroundSocket.onclose = () => {
                if (this.playgroundRunning) {
                    this.playgroundRunning = false;
                }
            };
        },

        clearPlayground() {
            this.playgroundInput = '';
            this.playgroundSteps = [];
            this.playgroundScenario = null;
            this.playgroundComplete = false;
            this.playgroundError = null;
            this.playgroundSummary = null;
        },

        // Cleanup on page unload
        init() {
            window.addEventListener('beforeunload', () => {
                if (this.testSocket) this.testSocket.close();
                if (this.benchmarkSocket) this.benchmarkSocket.close();
                if (this.playgroundSocket) this.playgroundSocket.close();
            });
        }
    }));
});
