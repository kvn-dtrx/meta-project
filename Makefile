# ---
# title: Makefile for meta-project
# ---

# ---

# After macos-habitat bootstrap: make install wires every user target

# ---

.PHONY: deploy-git-info-attributes deploy-git-lfs-storage help install install-user setup-dev

help: ## Displays available targets with description
	@printf '\n    After habitat:  make install\n\n'
	@printf '    %-16s: %s\n' \
	    "deploy-git-info-attributes" "Deploys private local Git attributes" \
	    "deploy-git-lfs-storage" "Deploys repository-local LFS storage" \
	    "install" "Alias for install-user" \
	    "install-user" "Runs make install-user across checkouts" \
	    "setup-dev" "Deploys Git policy and runs checkout dev setup"
	@printf '\n'

install: install-user ## Alias for install-user

install-user: ## Runs make install-user in each permanent/staged checkout
	@bin/install-checkouts.sh install-user

setup-dev: deploy-git-info-attributes deploy-git-lfs-storage ## Sets up development state across checkouts
	@bin/install-checkouts.sh setup-dev

deploy-git-info-attributes: ## Deploys private policy into .git/info/attributes
	@python3 bin/deploy-git-info-attributes.py "$(HOME)/data/projects"

deploy-git-lfs-storage: ## Deploys LFS storage from MY_NAS_DATA_DIR and mtdt
	@python3 bin/deploy-git-lfs-storage.py "$(HOME)/data/projects"
