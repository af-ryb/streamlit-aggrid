import {
  themeQuartz,
  themeAlpine,
  themeBalham,
  Theme,
  colorSchemeLight,
  colorSchemeLightWarm,
  colorSchemeLightCold,
  colorSchemeDark,
  colorSchemeDarkWarm,
  colorSchemeDarkBlue,
  iconSetQuartz,
  iconSetQuartzLight,
  iconSetQuartzBold,
  iconSetAlpine,
  iconSetMaterial,
  iconSetQuartzRegular,
  Part,
} from "ag-grid-community"

import isEmpty from "lodash/isEmpty"

import type { StreamlitThemeInfo } from "./types/AgGridTypes"

type StAggridThemeOptions = {
  themeName: string
  base: string
  params: Record<string, any>
  parts: string[]
}

class ThemeParser {
  private baseMapper: { [key: string]: Theme } = {
    quartz: themeQuartz,
    alpine: themeAlpine,
    balham: themeBalham,
  }

  private partsMapper: { [key: string]: Part } = {
    colorSchemeLight: colorSchemeLight,
    colorSchemeLightWarm: colorSchemeLightWarm,
    colorSchemeLightCold: colorSchemeLightCold,
    colorSchemeDark: colorSchemeDark,
    colorSchemeDarkWarm: colorSchemeDarkWarm,
    colorSchemeDarkBlue: colorSchemeDarkBlue,
    iconSetQuartz: iconSetQuartz(undefined),
    iconSetQuartzLight: iconSetQuartzLight,
    iconSetQuartzBold: iconSetQuartzBold,
    iconSetAlpine: iconSetAlpine,
    iconSetMaterial: iconSetMaterial,
    iconSetQuartzRegular: iconSetQuartzRegular,
  }

  streamlitRecipe(streamlitTheme: StreamlitThemeInfo): Theme {
    let theme: Theme = this.baseMapper["balham"]
    const font =
      streamlitTheme?.font?.split(",").at(1)?.trim() || "Source Sans Pro"
    const fontFamily = [font, { googleFont: font }]

    theme = theme
      .withParams({
        accentColor: streamlitTheme?.primaryColor,
        fontFamily: fontFamily,
        foregroundColor: streamlitTheme?.textColor,
        backgroundColor: streamlitTheme?.backgroundColor,
      })
      .withPart(iconSetQuartzLight)
      .withPart(this.partsMapper.iconSetQuartzRegular)

    if (streamlitTheme?.base === "dark") {
      theme = theme.withPart(colorSchemeDark)
    }

    return theme
  }

  alpineRecipe() {
    return themeAlpine
  }

  balhamRecipe() {
    return themeBalham
  }

  materialRecipe() {
    return themeAlpine.withPart(iconSetMaterial)
  }

  customRecipe(
    gridOptionsTheme: StAggridThemeOptions,
    streamlitTheme?: StreamlitThemeInfo
  ): Theme {
    const { base, params, parts } = gridOptionsTheme

    let theme: Theme = this.baseMapper[base]

    if (!isEmpty(params)) {
      theme = theme.withParams(params)
    }

    if (!isEmpty(parts)) {
      theme = parts.reduce((acc, partName) => {
        const part = this.partsMapper[partName]
        return acc.withPart(part)
      }, theme)
    }

    return theme
  }

  parse(
    gridOptionsTheme: StAggridThemeOptions,
    streamlitTheme?: StreamlitThemeInfo
  ): Theme {
    const { themeName } = gridOptionsTheme

    const recipeMapper: { [key: string]: () => Theme } = {
      streamlit: () => this.streamlitRecipe(streamlitTheme!),
      alpine: () => this.alpineRecipe(),
      balham: () => this.balhamRecipe(),
      material: () => this.materialRecipe(),
      custom: () => this.customRecipe(gridOptionsTheme, streamlitTheme),
    }

    const recipe = recipeMapper[themeName] || (() => themeBalham)
    return recipe()
  }
}

export { ThemeParser }
