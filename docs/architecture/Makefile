# AI Coder v3 - architecture docs (docs-as-code)
# Sources: architecture.md + diagrams/ + charts/; run from docs/architecture/.
# Targets: images charts html pdf docx all clean

DOC      = architecture
SRC      = $(DOC).md
CSS      = style.css
OUT      = out
IMG      = img

DOTS     = $(wildcard diagrams/*.dot)
MSCS     = $(wildcard diagrams/*.msc)
PNGS     = $(patsubst diagrams/%.dot,$(IMG)/%.png,$(DOTS)) \
           $(patsubst diagrams/%.msc,$(IMG)/%.png,$(MSCS))
GPLOTS   = $(wildcard charts/*.gp)
GP_PNGS  = $(IMG)/token-growth.png

.PHONY: all images charts html pdf docx clean

all: images charts html pdf docx
	@echo "== done: out/$(DOC).{html,pdf,docx}"

images: $(PNGS)

$(IMG)/%.png: diagrams/%.dot
	@mkdir -p $(IMG)
	dot -Tpng $< -o $@

$(IMG)/%.png: diagrams/%.msc
	@mkdir -p $(IMG)
	mscgen -T png -o $@ $<

charts: $(GP_PNGS)

$(GP_PNGS): $(GPLOTS)
	@mkdir -p $(IMG)
	gnuplot $<

html: $(PNGS) $(GP_PNGS)
	@mkdir -p $(OUT)
	pandoc $(SRC) --standalone --embed-resources --toc --toc-depth=2 --css=$(CSS) -o $(OUT)/$(DOC).html

pdf: $(PNGS) $(GP_PNGS)
	@mkdir -p $(OUT)
	pandoc $(SRC) --standalone --embed-resources --css=$(CSS) -o $(OUT)/print.html
	weasyprint $(OUT)/print.html $(OUT)/$(DOC).pdf

docx: $(PNGS) $(GP_PNGS)
	@mkdir -p $(OUT)
	pandoc $(SRC) --toc -o $(OUT)/$(DOC).docx

clean:
	rm -rf $(OUT) $(IMG)