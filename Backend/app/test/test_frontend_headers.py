"""The CSP that ships, checked against the shipped bundle.

`web/public/_headers` is a Cloudflare Pages file, so nothing in the repository
proves its directives actually fit the built app - and a policy that guesses
wrong does not warn, it breaks sign-in silently on the production origin.

This reads the real `_headers`, asserts the directives that are known to be
required, then asserts that `npm run build` produced a bundle that asks for
exactly those origins. It needs no server and no browser: the failure mode it is
guarding against is a policy edited without re-checking what the page loads.
"""

import re
import pathlib

import pytest

WEB = pathlib.Path(__file__).resolve().parents[3] / "web"
HEADERS = WEB / "public" / "_headers"
DIST = WEB / "dist"

if not HEADERS.exists():
    pytest.skip("web/public/_headers is not in this checkout", allow_module_level=True)


def policy() -> str:
    text = HEADERS.read_text()
    match = re.search(r"^  Content-Security-Policy: (.+)$", text, re.MULTILINE)
    assert match, "no Content-Security-Policy in web/public/_headers"
    return match.group(1).strip()


def directives() -> dict[str, str]:
    return {
        part.split()[0]: part[len(part.split()[0]) + 1 :]
        for part in policy().split("; ")
        if part.strip()
    }


def test_every_render_service_the_frontend_talks_to_is_allowed():
    """Render gives each service `<name>.onrender.com`, and the site calls two.

    Renaming a service without editing this policy is a blank page or a dead
    upload button, and neither failure has an error message a student would see.
    """
    blueprint_path = WEB.parent / "render.yaml"
    if not blueprint_path.exists():
        pytest.skip("no render.yaml in this checkout")
    blueprint = blueprint_path.read_text()
    names = re.findall(r"^  - type: web\n    name: (\S+)", blueprint, re.MULTILINE)
    assert names, "no web services in render.yaml"
    connect = directives()["connect-src"]
    for name in names:
        assert f"https://{name}.onrender.com" in connect, f"{name} is not in connect-src"


def test_scripts_and_styles_cannot_be_injected():
    got = directives()
    assert "unsafe-eval" not in got["script-src"]
    assert "'unsafe-inline'" not in got["script-src"]
    assert got["object-src"] == "'none'"
    assert got["base-uri"] == "'self'"
    assert got["form-action"] == "'self'"
    assert got["frame-ancestors"] == "'none'"
    # Google's sign-in library styles the button it builds in this document, so
    # style-src has to allow inline styles. script-src must not.
    assert "unsafe-inline" in got["style-src"]
    assert "https://accounts.google.com" in got["style-src"]


def test_every_subresource_the_built_bundle_loads_is_allowed():
    """Each rule here is triggered by something the artifact actually loads.

    Scanning the bundle for every URL is not a check - React and Tailwind carry
    documentation links in their error strings, and an SVG namespace is not a
    network fetch. So each directive below is only asserted when the built page
    proves it needs it.
    """
    assets = list((DIST / "assets").glob("*.js"))
    if not assets:
        pytest.skip("run npm run build in web/ first")
    js = "".join(file.read_bytes().decode("latin-1") for file in assets)
    html = (DIST / "index.html").read_bytes().decode("latin-1")
    got = directives()

    if "gsi/client" in js or "accounts.google.com" in js:
        assert "https://accounts.google.com" in got["script-src"]
        assert "https://accounts.google.com" in got["frame-src"]
    if "fonts.googleapis.com" in html:
        assert "https://fonts.googleapis.com" in got["style-src"]
        assert "https://fonts.gstatic.com" in got["font-src"]
    if "createObjectURL" in js:  # the reader turns page bytes into blob: images
        assert "blob:" in got["img-src"]

    # Vite inlines VITE_API_URL as a literal, so the built bundle states the API
    # origin it will actually call. A fetch to an origin connect-src does not
    # list fails without a visible message, which is how a mis-set Pages
    # variable reads to a student as "the site is broken".
    for origin in set(re.findall(r"https://[a-z0-9.-]+\.onrender\.com", js)):
        assert origin in got["connect-src"], f"{origin} is called but not allowed"


def test_only_the_assets_rule_sets_cache_control():
    """Pages combines every matching block instead of letting the specific one win.

    A Cache-Control on /* therefore reaches the hashed bundle too, and the two
    values arrive glued together as "no-store, public, max-age=..., immutable",
    which browsers honour as no-store: the whole app re-downloaded on every
    load. This was measured on the deployed site on 2026-11-07.
    """
    text = HEADERS.read_text()
    everything = text.split("\n/*\n", 1)[1].split("/assets/*", 1)[0]
    assert "Cache-Control" not in everything, (
        "a Cache-Control on /* merges into the asset response and kills the "
        "immutable cache; documents already get must-revalidate from Pages"
    )

    assets = text.split("/assets/*", 1)[1]
    assert "immutable" in assets
    assert "max-age=31536000" in assets
    # The patterns name paths, not files: /index.html would never match a route.
    rules = "\n".join(
        line
        for line in text.splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    )
    assert "/index.html" not in rules, "a rule named after the file never matches a route"
    assert rules.index("/*") < rules.index("/assets/*")
