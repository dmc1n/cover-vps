# S2DIO covers CLI

Install with `uv tool install ./clients/cli` or `pipx install ./clients/cli`.

```sh
covers kinds
covers kinds --kind sofa
covers find --kind sofa --width 230 --depth 90 --height 85
covers find --kind sofa --width 230 --depth 90 --height 85 --front-height 60 --json
covers find --kind corner_sofa --long-side 300 --short-side 220 --depth 95 --height 80 --left-right left
covers quote --kind dining_set --width 220 --depth 100 --height 75 --support balloons
covers quote --kind table --width 220 --depth 100 --height 75 --no-chairs
covers link --kind sofa --width 230 --depth 90 --height 85
covers cover suns-2-seater-kota
```

`COVERS_API` overrides the default `https://preview.s2dio.living/api/v2`.
`COVERS_API_KEY` supplies a partner key via `X-Api-Key`. `--api` and `--key`
override these variables and work before or after the command. Prefer the
key environment variable to keep credentials out of shell history.
`--json` prints the API JSON, including HTTP errors.

Open with limits: API access is subject to rate limits. On HTTP 429, respect
Retry-After before retrying. Exit codes: 0 success, 2 caller input (4xx),
3 rate limited, 1 network/server failure.

A person always pays: these commands find covers, quote prices, and create
links. A person orders and pays on the site; nothing is ordered by this command.
