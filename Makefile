# ---
# title: Makefile for meta-project
# ---

# ---

# After macos-habitat bootstrap: make install wires every checkout

# ---

.PHONY: deploy-git-info-attributes help install

help: ## Displays available targets with description
	@printf '\n    After habitat:  make install\n\n'
	@printf '    %-16s: %s\n' \
	    "deploy-git-info-attributes" "Deploys private local Git attributes" \
	    "install" "Runs make install in permanent/staged checkouts"
	@printf '\n'

install: deploy-git-info-attributes ## Runs make install in each permanent/staged checkout
	@bin/install-checkouts.sh

deploy-git-info-attributes: ## Deploys private policy into .git/info/attributes
	@python3 bin/deploy-git-info-attributes.py "$(HOME)/data/projects"
