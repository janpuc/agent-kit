import { existsSync } from "node:fs"
import { dirname, join, resolve } from "node:path"
import { fileURLToPath } from "node:url"

const pluginRoot = dirname(fileURLToPath(import.meta.url))
const bundledSkills = join(pluginRoot, "skills")
const canonicalSkills = resolve(pluginRoot, "..", "..", "skills")
const skillsDirectory = existsSync(bundledSkills) ? bundledSkills : canonicalSkills

export const AgentKit = async () => ({
  config: async (config) => {
    config.skills ??= {}
    config.skills.paths ??= []
    if (!config.skills.paths.includes(skillsDirectory)) {
      config.skills.paths.push(skillsDirectory)
    }
  },
})
