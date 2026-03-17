# KGS Bot Debug

E2E testing and debugging tools for kgs-bot and kgs-bot-monitor integration.

## Purpose

This repository provides automated testing infrastructure to help debug and fix tricky bugs in the interaction between:
- `kgs-bot`: The main bot application
- `kgs-bot-monitor`: The monitoring application

## Structure

```
kgs-bot-debug/
├── tests/              # E2E test suites
├── fixtures/           # Test data and mocks
├── scripts/            # Helper scripts for debugging
├── config/             # Test configuration
└── reports/            # Test reports and logs
```

## Getting Started

1. Install dependencies
2. Configure test environment
3. Run tests: `pytest tests/`

## Contributing

Add new test cases to reproduce bugs and validate fixes.