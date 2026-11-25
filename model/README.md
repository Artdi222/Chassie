# Live2D models

Chassie does not ship a model. Put any Cubism 3/4 Live2D model here, one folder per model:

```
model/
└── MyModel/
    ├── MyModel.model3.json
    ├── MyModel.moc3
    ├── MyModel.physics3.json
    ├── textures/…
    └── expressions/…   (optional .exp3.json files)
```

Chassie finds every `*.model3.json` under this folder on startup. Pick the model in the
desktop **Model** panel (or the web studio). The folder name is the model's id.

Everything in this folder except this README is ignored by git, so your models stay local.
Respect each model's licence: most free models allow personal use but not redistribution.
