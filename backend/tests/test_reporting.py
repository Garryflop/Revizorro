"""HTML report post-processing."""

from revizorro.reporting.renderer import link_references


def test_references_link_to_the_place_where_they_are_defined():
    html = (
        "<h4>R-02 · функциональное</h4><p>См. F-003 и F-009.</p>"
        "<ol><li><strong>F-003 · Однозначность.</strong> Связано с R-02 и R-99.</li></ol>"
        "<h3>Q-01 → аналитик</h3><p>Снимает F-003.</p><p><code>R-02</code></p>"
    )
    out = link_references(html, merged={"F-009": "F-003"})

    assert '<h4 id="R-02">R-02 · функциональное</h4>' in out  # anchor, and no link inside a heading
    assert '<strong id="F-003">F-003 · Однозначность.</strong>' in out  # a definition does not link to itself
    assert 'См. <a class="ref" href="#F-003">F-003</a>' in out
    assert '<a class="ref" href="#F-003">F-009</a>' in out  # merged finding leads to the one that stayed
    assert 'Связано с <a class="ref" href="#R-02">R-02</a> и R-99.' in out  # unknown ids stay plain text
    assert 'Снимает <a class="ref" href="#F-003">F-003</a>' in out
    assert "<code>R-02</code>" in out
