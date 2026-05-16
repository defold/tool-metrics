class ToolMetricsDashboard {
    constructor() {
        this.rows = [];
        this.filteredRows = [];
        this.charts = new Map();
        this.palette = [
            "#2563eb",
            "#059669",
            "#d97706",
            "#7c3aed",
            "#be123c",
            "#0f766e",
            "#475569",
        ];
        this.failureColor = "#dc2626";
        this.metrics = [
            {
                field: "install_size_bytes",
                containerId: "install-size-chart",
                title: "Install Size",
                unit: "mb",
                scale: 1024 * 1024,
            },
            {
                field: "bob_build_time_ms",
                containerId: "bob-build-time-chart",
                title: "Bob Build Time",
                unit: "seconds",
                scale: 1000,
            },
            {
                field: "open_time_ms",
                containerId: "open-time-chart",
                title: "Open Time",
                unit: "seconds",
                scale: 1000,
            },
            {
                field: "memory_after_open_bytes",
                containerId: "memory-after-open-chart",
                title: "Memory After Open",
                unit: "mb",
                scale: 1024 * 1024,
            },
            {
                field: "build_time_ms",
                containerId: "build-time-chart",
                title: "Build Time",
                unit: "seconds",
                scale: 1000,
            },
            {
                field: "memory_added_by_build_bytes",
                containerId: "memory-added-by-build-chart",
                title: "Memory Added By Build",
                unit: "mb",
                scale: 1024 * 1024,
            },
        ];

        this.elements = {
            sampleLimitFilter: document.getElementById("sample-limit-filter"),
            lastUpdated: document.getElementById("last-updated"),
            summaryCommit: document.getElementById("summary-commit"),
            summaryRelease: document.getElementById("summary-release"),
            summaryTarget: document.getElementById("summary-target"),
        };
    }

    async init() {
        this.setLoading();
        this.bindEvents();

        try {
            this.rows = await this.loadRows();
            this.rows.sort((a, b) => a.commitDate - b.commitDate);
            this.applyFilters();
        } catch (error) {
            console.error("Failed to load metrics dashboard", error);
            this.showError("Failed to load ../data/metrics.csv");
        }
    }

    bindEvents() {
        this.elements.sampleLimitFilter.addEventListener("change", () => this.applyFilters());

        window.addEventListener("resize", () => {
            for (const containerId of this.charts.keys()) {
                Plotly.Plots.resize(document.getElementById(containerId));
            }
        });
    }

    async loadRows() {
        const response = await fetch("../data/metrics.csv");
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}`);
        }

        const parsed = this.parseCSV(await response.text());
        return parsed
            .map((row) => {
                const commitDate = new Date(row.commit_time);
                return { ...row, commitDate };
            })
            .filter((row) => row.commit_time && !Number.isNaN(row.commitDate.getTime()));
    }

    parseCSV(text) {
        const lines = text.trim().split(/\r?\n/).filter(Boolean);
        if (lines.length === 0) {
            return [];
        }

        const headers = this.parseCSVLine(lines[0]);
        return lines.slice(1).map((line) => {
            const values = this.parseCSVLine(line);
            const row = {};
            headers.forEach((header, index) => {
                row[header] = values[index] || "";
            });
            return row;
        });
    }

    parseCSVLine(line) {
        const values = [];
        let value = "";
        let inQuotes = false;

        for (let index = 0; index < line.length; index += 1) {
            const char = line[index];
            if (char === "\"") {
                if (inQuotes && line[index + 1] === "\"") {
                    value += "\"";
                    index += 1;
                } else {
                    inQuotes = !inQuotes;
                }
            } else if (char === "," && !inQuotes) {
                values.push(value.trim());
                value = "";
            } else {
                value += char;
            }
        }

        values.push(value.trim());
        return values;
    }

    applyFilters() {
        const sampleLimit = parseInt(this.elements.sampleLimitFilter.value, 10);
        let rows = this.rows;

        if (Number.isFinite(sampleLimit) && rows.length > sampleLimit) {
            rows = rows.slice(rows.length - sampleLimit);
        }

        this.filteredRows = rows;
        this.updateSummary();
        this.renderCharts();
    }

    updateSummary() {
        const latest = this.filteredRows[this.filteredRows.length - 1];
        if (!latest) {
            this.elements.lastUpdated.textContent = "-";
            this.elements.summaryCommit.textContent = "-";
            this.elements.summaryRelease.textContent = "-";
            this.elements.summaryTarget.textContent = "-";
            return;
        }

        this.elements.lastUpdated.textContent = this.formatDateTime(latest.commitDate);
        this.elements.summaryCommit.textContent = this.shortSha(latest.commit_sha);
        this.elements.summaryCommit.title = latest.commit_sha || "";
        this.elements.summaryRelease.textContent = latest.release_tag || "-";
        this.elements.summaryTarget.textContent = [latest.platform, latest.project].filter(Boolean).join(" / ") || "-";
        this.elements.summaryTarget.title = this.elements.summaryTarget.textContent;
    }

    renderCharts() {
        this.metrics.forEach((metric) => this.renderChart(metric));
    }

    renderChart(metric) {
        const container = document.getElementById(metric.containerId);
        const rowsWithValues = this.filteredRows.filter((row) => this.metricValue(row, metric.field) !== null);

        if (rowsWithValues.length === 0) {
            Plotly.purge(metric.containerId);
            this.charts.delete(metric.containerId);
            container.innerHTML = "<div class=\"empty\">No data for the current filters.</div>";
            return;
        }

        const traces = this.buildTraces(rowsWithValues, metric);
        const decorations = this.buildCommentDecorations(rowsWithValues);
        const isMobile = window.innerWidth <= 720;
        const layout = {
            title: {
                text: metric.title,
                font: { size: 16, color: "#111827" },
                y: 0.96,
            },
            xaxis: {
                title: "Commit time",
                gridcolor: "#eef2f7",
                tickformat: "%b %d",
            },
            yaxis: {
                title: this.axisTitle(metric.unit),
                gridcolor: "#eef2f7",
                tickformat: ".2f",
            },
            margin: {
                l: isMobile ? 58 : 78,
                r: 28,
                t: 48,
                b: isMobile ? 86 : 76,
            },
            paper_bgcolor: "#ffffff",
            plot_bgcolor: "#ffffff",
            shapes: decorations.shapes,
            annotations: decorations.annotations,
            showlegend: traces.length > 1,
            legend: {
                orientation: "h",
                x: 0,
                y: -0.22,
                font: { size: 12 },
            },
            hovermode: "closest",
        };
        const config = {
            displayModeBar: true,
            modeBarButtonsToRemove: ["select2d", "lasso2d"],
            displaylogo: false,
            responsive: true,
        };

        Plotly.purge(metric.containerId);
        container.innerHTML = "";
        Plotly.newPlot(metric.containerId, traces, layout, config);
        this.charts.set(metric.containerId, true);
    }

    buildTraces(rows, metric) {
        const grouped = new Map();
        rows.forEach((row) => {
            const key = this.seriesName(row);
            if (!grouped.has(key)) {
                grouped.set(key, []);
            }
            grouped.get(key).push(row);
        });

        return [...grouped.entries()].map(([name, groupRows], index) => {
            const color = this.palette[index % this.palette.length];
            groupRows.sort((a, b) => a.commitDate - b.commitDate);
            return {
                x: groupRows.map((row) => row.commit_time),
                y: groupRows.map((row) => this.displayValue(row, metric)),
                type: "scatter",
                mode: "lines+markers",
                name,
                line: { color, width: 2 },
                marker: {
                    size: 7,
                    color: groupRows.map((row) => row.status === "ok" ? color : this.failureColor),
                    line: {
                        width: groupRows.map((row) => row.status === "ok" ? 0 : 1),
                        color: "#7f1d1d",
                    },
                },
                text: groupRows.map((row) => this.hoverText(row, metric, name)),
                hovertemplate: "%{text}<extra></extra>",
            };
        });
    }

    hoverText(row, metric, seriesName) {
        const lines = [
            `<b>${this.escapeHtml(seriesName)}</b>`,
            `Time: ${this.escapeHtml(row.commit_time)}`,
            `Value: ${this.escapeHtml(this.formatMetric(this.displayValue(row, metric), metric.unit))}`,
            `Commit: ${this.escapeHtml(this.shortSha(row.commit_sha))}`,
            `Release: ${this.escapeHtml(row.release_tag || "-")}`,
            `Status: ${this.escapeHtml(row.status || "-")}`,
        ];
        if (row.error) {
            lines.push(`Error: ${this.escapeHtml(row.error)}`);
        }
        if (row.comment) {
            lines.push(`Comment: ${this.escapeHtml(row.comment)}`);
        }
        return lines.join("<br>");
    }

    buildCommentDecorations(rows) {
        const seen = new Set();
        const comments = rows
            .filter((row) => row.comment && row.comment.trim())
            .filter((row) => {
                const key = `${row.commit_time}:${row.comment}`;
                if (seen.has(key)) return false;
                seen.add(key);
                return true;
            });

        return {
            shapes: comments.map((row) => ({
                type: "line",
                xref: "x",
                x0: row.commit_time,
                x1: row.commit_time,
                yref: "paper",
                y0: 0,
                y1: 1,
                line: {
                    color: "#64748b",
                    width: 1,
                    dash: "dot",
                },
            })),
            annotations: comments.map((row) => ({
                x: row.commit_time,
                y: 0.98,
                xref: "x",
                yref: "paper",
                text: this.shorten(row.comment.trim(), 22),
                showarrow: false,
                textangle: -90,
                xanchor: "left",
                yanchor: "top",
                xshift: 4,
                font: {
                    color: "#475569",
                    size: 11,
                },
            })),
        };
    }

    seriesName(row) {
        return [row.platform, row.project].filter(Boolean).join(" / ") || "metrics";
    }

    metricValue(row, field) {
        const raw = (row[field] || "").trim();
        if (!raw) return null;
        const value = Number(raw);
        return Number.isFinite(value) ? value : null;
    }

    displayValue(row, metric) {
        const value = this.metricValue(row, metric.field);
        if (value === null) return null;
        return value / metric.scale;
    }

    axisTitle(unit) {
        return unit === "mb" ? "MB" : "Seconds";
    }

    formatMetric(value, unit) {
        if (value === null) return "-";
        if (unit === "mb") {
            return `${value.toFixed(2)} MB`;
        }
        if (unit === "seconds") {
            return `${value.toFixed(2)} s`;
        }
        return value.toFixed(2);
    }

    formatDateTime(date) {
        return date.toISOString().replace(".000Z", "Z");
    }

    shortSha(value) {
        return value ? value.slice(0, 12) : "-";
    }

    shorten(value, limit) {
        return value.length <= limit ? value : `${value.slice(0, limit - 1)}...`;
    }

    escapeHtml(value) {
        return String(value).replace(/[&<>"']/g, (char) => ({
            "&": "&amp;",
            "<": "&lt;",
            ">": "&gt;",
            "\"": "&quot;",
            "'": "&#39;",
        }[char]));
    }

    setLoading() {
        this.metrics.forEach((metric) => {
            const container = document.getElementById(metric.containerId);
            container.innerHTML = "<div class=\"loading\">Loading chart...</div>";
        });
    }

    showError(message) {
        this.metrics.forEach((metric) => {
            const container = document.getElementById(metric.containerId);
            container.innerHTML = `<div class="error">${message}</div>`;
        });
    }
}

document.addEventListener("DOMContentLoaded", () => {
    new ToolMetricsDashboard().init();
});
