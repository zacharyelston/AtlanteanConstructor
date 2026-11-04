# Working in AtlanteanConstructor

- **Branches and PRs:** make every change on a branch (`feat/…`, `fix/…`, `chore/…`) and open a PR into `main`. Never push to `main` directly. GitHub branch protection isn't available while the repo is private on the free plan, so this rule is the guard.
- **Naming:** write the sibling tractor project as **eOx** in prose, titles, vehicle names and figures. Keep the GitHub slug `zacharyelston/EOx` in links and cross-repo references, and keep lowercase code names (`eox_vehicle.py`).
- **Kept runs:** `ring_engine/output/` is gitignored scratch space. Runs worth keeping are copied to `runs/<date>_<name>/` and listed in `runs/README.md`. Never edit an archived run.
- **Figures:** README images live in `docs/img/`. `tools/make_figs.py` redraws the SVGs from `runs/`.
- **Planning:** the shared GitHub Project is https://github.com/users/zacharyelston/projects/7.
