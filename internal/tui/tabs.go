package tui

type tabSpec struct {
	ID    string
	Title string
}

const (
	tabIDRun      = "run"
	tabIDPRD      = "prd"
	tabIDSettings = "settings"
	tabIDEnv      = "env"
	tabIDPrompt   = "prompt"
	tabIDLogs     = "logs"
	tabIDProgress = "progress"
	tabIDHelp     = "help"
)

var defaultTabSpecs = []tabSpec{
	{ID: tabIDRun, Title: "Run"},
	{ID: tabIDPRD, Title: "PRD"},
	{ID: tabIDSettings, Title: "Settings"},
	{ID: tabIDEnv, Title: "Env"},
	{ID: tabIDPrompt, Title: "Prompt"},
	{ID: tabIDLogs, Title: "Logs"},
	{ID: tabIDProgress, Title: "Progress"},
	{ID: tabIDHelp, Title: "Help"},
}

var tabIDOrder = func() []string {
	order := make([]string, len(defaultTabSpecs))
	for i, spec := range defaultTabSpecs {
		order[i] = spec.ID
	}
	return order
}()

func defaultTabIDs() []string {
	ids := make([]string, len(defaultTabSpecs))
	for i, spec := range defaultTabSpecs {
		ids[i] = spec.ID
	}
	return ids
}

func tabTitle(id string) string {
	for _, spec := range defaultTabSpecs {
		if spec.ID == id {
			return spec.Title
		}
	}
	return id
}
