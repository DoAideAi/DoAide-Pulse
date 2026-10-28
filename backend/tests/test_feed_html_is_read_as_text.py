"""A feed's HTML is read as the text a reader would see, not passed on as markup.

RSS descriptions are HTML by convention, in CDATA or entity-escaped, and
``itertext`` returns that markup as a string. Every consumer treats an entry
as plain text — the headline becomes a post title, and a template substitutes
``{{signal.summary}}`` straight into a draft's body — so a feed's ``<script>``
and ``<img onerror>`` arrived in drafts verbatim and titles showed their tags.
"""
from __future__ import annotations

from app.services import feeds

RSS = b"""<?xml version="1.0"?>
<rss version="2.0"><channel><title>Changelog</title>
<item>
  <title>Release &lt;b&gt;v2.0&lt;/b&gt; &amp; friends</title>
  <link>https://example.com/v2</link>
  <guid>v2</guid>
  <description><![CDATA[<p>Faster <em>builds</em>.</p><script>alert(1)</script>
  <img src=x onerror="alert(2)"><style>p{}</style><p>Second&nbsp;para &amp; more</p>]]></description>
</item>
</channel></rss>"""

ATOM = b"""<?xml version="1.0"?>
<feed xmlns="http://www.w3.org/2005/Atom"><title>Log</title>
<entry><id>e1</id><title type="html">&lt;i&gt;Shipped&lt;/i&gt;</title>
<content type="html">&lt;p&gt;Hi&lt;/p&gt;&lt;iframe src="https://evil"&gt;&lt;/iframe&gt;</content>
</entry></feed>"""


def test_rss_title_and_description_lose_their_markup():
    entry = feeds.parse(RSS).entries[0]

    assert entry.title == "Release v2.0 & friends"
    assert "<" not in entry.summary
    assert "alert" not in entry.summary
    assert "Faster builds." in entry.summary
    assert "Second\xa0para & more" in entry.summary or "Second para & more" in entry.summary


def test_atom_html_title_and_content_lose_their_markup():
    entry = feeds.parse(ATOM).entries[0]

    assert entry.title == "Shipped"
    assert entry.summary == "Hi"


def test_plain_text_is_left_exactly_as_it_was():
    assert feeds._plain("5 < 6 and AT&T") == "5 < 6 and AT&T"
    assert feeds._plain("  spaced  ") == "  spaced  "
