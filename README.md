# Stock Income Agent

Personal, self-hosted agent that generates monthly income from a paper-traded S&P 500 portfolio using dividends + covered calls.

See `docs/superpowers/specs/2026-05-28-stock-income-agent-design.md` for the full design.

## Local development

Copy `.env.example` to `.env.local` and fill in values. Then:

```
make up        # start all containers
make logs      # follow logs
make down      # stop everything
make test      # run all tests
```

Dashboard: http://localhost:3000
API: http://localhost:8000
Health: http://localhost:8000/health
