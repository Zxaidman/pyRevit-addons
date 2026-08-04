# -*- coding: utf-8 -*-
"""theme - pyRevit palette lookup and WPF control templates.

The reason pyRevit's own forms explode under CPython is ``wpf.LoadComponent``,
which is an IronPython-only module. **XAML itself is fine.**
``System.Windows.Markup.XamlReader.Parse`` is a plain .NET API and works
identically under pythonnet, so the control templates below are the ones from
pyRevit's ProgressBar.xaml, parsed at runtime.

Event handlers are the one thing that cannot survive the trip:
``Click="clicked_cancel"`` needs a code-behind class for the parser to bind
against. So only the *styles* are parsed here, and the controls that use them
are built in code with their events wired up normally.
"""

__version__ = "1.5.0"
__all__ = ["brush", "color", "DARK_FALLBACK", "ACCENT_FALLBACK",
           "ACCENT_COLOR_FALLBACK", "bar_resources"]

try:
    import clr
    for _asm in ("PresentationFramework", "PresentationCore", "WindowsBase",
                 "System.Xaml"):
        try:
            clr.AddReference(_asm)
        except Exception:
            pass
except ImportError:
    pass

from System.Windows.Media import BrushConverter, ColorConverter

#: Used only when the pyRevit resources are not reachable (bare add-in, or a
#: pyRevit build that renames them). Not a claim about pyRevit's real values.
DARK_FALLBACK = "#FF2C3E50"
ACCENT_FALLBACK = "#FFF39C12"
ACCENT_COLOR_FALLBACK = "#FFF39C12"


def _app_resource(key):
    try:
        from System.Windows import Application
        app = Application.Current
        if app is not None:
            return app.TryFindResource(key)
    except Exception:
        pass
    return None


def brush(key, fallback):
    """Resolve a brush from the running application's resources.

    Inside pyRevit this returns the real themed brush, so the bar follows the
    user's pyRevit theme (including dark mode) instead of hardcoding colours.
    """
    found = _app_resource(key)
    if found is not None:
        return found
    try:
        return BrushConverter().ConvertFromString(fallback)
    except Exception:
        return None


def color(key, fallback):
    found = _app_resource(key)
    if found is not None:
        return found
    try:
        return ColorConverter().ConvertFromString(fallback)
    except Exception:
        return None


# ---------------------------------------------------------------------------
# control templates, lifted from pyRevit's ProgressBar.xaml
# ---------------------------------------------------------------------------

_BAR_XAML = u"""
<ResourceDictionary
    xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation"
    xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml">

  <Style TargetType="{x:Type Button}">
    <Setter Property="FocusVisualStyle" Value="{x:Null}"/>
    <Setter Property="Background" Value="#ffffff"/>
    <Setter Property="BorderBrush" Value="#cccccc"/>
    <Setter Property="BorderThickness" Value="0"/>
    <Setter Property="Foreground" Value="{DynamicResource pyRevitDarkBrush}"/>
    <Setter Property="HorizontalContentAlignment" Value="Center"/>
    <Setter Property="VerticalContentAlignment" Value="Center"/>
    <Setter Property="Padding" Value="8,2,8,2"/>
    <Setter Property="Template">
      <Setter.Value>
        <ControlTemplate TargetType="{x:Type Button}">
          <Border Background="{TemplateBinding Background}"
                  BorderBrush="{TemplateBinding BorderBrush}"
                  BorderThickness="{TemplateBinding BorderThickness}"
                  CornerRadius="10"
                  SnapsToDevicePixels="true">
            <ContentPresenter Name="Presenter"
                              Margin="{TemplateBinding Padding}"
                              VerticalAlignment="{TemplateBinding VerticalContentAlignment}"
                              HorizontalAlignment="{TemplateBinding HorizontalContentAlignment}"
                              RecognizesAccessKey="True"
                              SnapsToDevicePixels="{TemplateBinding SnapsToDevicePixels}"/>
          </Border>
          <ControlTemplate.Triggers>
            <Trigger Property="IsEnabled" Value="false">
              <Setter Property="Foreground" Value="{DynamicResource pyRevitDarkBrush}"/>
            </Trigger>
            <Trigger Property="IsMouseOver" Value="True">
              <Setter Property="Background" Value="#dddddd"/>
              <Setter Property="BorderBrush" Value="#cccccc"/>
              <Setter Property="Foreground" Value="{DynamicResource pyRevitDarkBrush}"/>
            </Trigger>
            <Trigger Property="IsPressed" Value="True">
              <Setter Property="Background" Value="{DynamicResource pyRevitAccentBrush}"/>
              <Setter Property="BorderBrush" Value="{DynamicResource pyRevitAccentBrush}"/>
              <Setter Property="Foreground" Value="#ffffff"/>
            </Trigger>
            <Trigger Property="IsFocused" Value="true">
              <Setter Property="BorderBrush" Value="{DynamicResource pyRevitAccentBrush}"/>
            </Trigger>
          </ControlTemplate.Triggers>
        </ControlTemplate>
      </Setter.Value>
    </Setter>
  </Style>

  <Style TargetType="{x:Type ProgressBar}">
    <Setter Property="Background" Value="{DynamicResource pyRevitDarkBrush}"/>
    <Setter Property="Foreground" Value="{DynamicResource pyRevitAccentBrush}"/>
    <Setter Property="BorderBrush" Value="{x:Null}"/>
    <Setter Property="BorderThickness" Value="0"/>
    <Setter Property="IsTabStop" Value="False"/>
    <Setter Property="Maximum" Value="100"/>
    <Setter Property="Template">
      <Setter.Value>
        <ControlTemplate TargetType="ProgressBar">
          <Grid x:Name="Root">
            <Border x:Name="PART_Track"
                    Background="{TemplateBinding Background}"
                    BorderBrush="{TemplateBinding BorderBrush}"
                    BorderThickness="{TemplateBinding BorderThickness}"/>
            <Grid x:Name="ProgressBarRootGrid">
              <Grid x:Name="IndeterminateRoot" Visibility="Collapsed">
                <Rectangle x:Name="IndeterminateSolidFill"
                           Margin="{TemplateBinding BorderThickness}"
                           Fill="{DynamicResource pyRevitAccentBrush}"
                           Opacity="1"
                           RenderTransformOrigin="0.5,0.5"
                           StrokeThickness="0"/>
                <Rectangle x:Name="IndeterminateGradientFill"
                           Opacity=".2"
                           Margin="{TemplateBinding BorderThickness}"
                           StrokeThickness="1">
                  <Rectangle.Fill>
                    <LinearGradientBrush MappingMode="Absolute"
                                         SpreadMethod="Repeat"
                                         StartPoint="20,1" EndPoint="0,1">
                      <LinearGradientBrush.Transform>
                        <TransformGroup>
                          <TranslateTransform x:Name="xTransform" X="0"/>
                          <SkewTransform AngleX="-30"/>
                        </TransformGroup>
                      </LinearGradientBrush.Transform>
                      <GradientStop Offset="0" Color="{DynamicResource pyRevitAccentColor}"/>
                      <GradientStop Offset="0.499" Color="{DynamicResource pyRevitAccentColor}"/>
                      <GradientStop Offset="0.500" Color="White"/>
                      <GradientStop Offset="1.0" Color="White"/>
                    </LinearGradientBrush>
                  </Rectangle.Fill>
                </Rectangle>
              </Grid>
              <Grid x:Name="DeterminateRoot">
                <Border x:Name="PART_Indicator"
                        HorizontalAlignment="Left"
                        Background="{DynamicResource pyRevitAccentBrush}"/>
              </Grid>
            </Grid>
            <VisualStateManager.VisualStateGroups>
              <VisualStateGroup x:Name="CommonStates">
                <VisualState x:Name="Determinate"/>
                <VisualState x:Name="Indeterminate">
                  <Storyboard RepeatBehavior="Forever">
                    <ObjectAnimationUsingKeyFrames Storyboard.TargetName="IndeterminateRoot"
                                                   Storyboard.TargetProperty="(UIElement.Visibility)"
                                                   Duration="00:00:00">
                      <DiscreteObjectKeyFrame KeyTime="00:00:00">
                        <DiscreteObjectKeyFrame.Value>
                          <Visibility>Visible</Visibility>
                        </DiscreteObjectKeyFrame.Value>
                      </DiscreteObjectKeyFrame>
                    </ObjectAnimationUsingKeyFrames>
                    <ObjectAnimationUsingKeyFrames Storyboard.TargetName="DeterminateRoot"
                                                   Storyboard.TargetProperty="(UIElement.Visibility)"
                                                   Duration="00:00:00">
                      <DiscreteObjectKeyFrame KeyTime="00:00:00">
                        <DiscreteObjectKeyFrame.Value>
                          <Visibility>Collapsed</Visibility>
                        </DiscreteObjectKeyFrame.Value>
                      </DiscreteObjectKeyFrame>
                    </ObjectAnimationUsingKeyFrames>
                    <DoubleAnimationUsingKeyFrames Storyboard.TargetName="xTransform"
                                                   Storyboard.TargetProperty="X">
                      <SplineDoubleKeyFrame KeyTime="0" Value="0"/>
                      <SplineDoubleKeyFrame KeyTime="00:00:.35" Value="20"/>
                    </DoubleAnimationUsingKeyFrames>
                  </Storyboard>
                </VisualState>
              </VisualStateGroup>
            </VisualStateManager.VisualStateGroups>
          </Grid>
          <ControlTemplate.Triggers>
            <Trigger Property="Orientation" Value="Vertical">
              <Setter TargetName="Root" Property="LayoutTransform">
                <Setter.Value>
                  <RotateTransform Angle="-90"/>
                </Setter.Value>
              </Setter>
            </Trigger>
            <Trigger Property="IsIndeterminate" Value="true">
              <Setter TargetName="DeterminateRoot" Property="Visibility" Value="Collapsed"/>
              <Setter TargetName="IndeterminateRoot" Property="Visibility" Value="Visible"/>
            </Trigger>
          </ControlTemplate.Triggers>
        </ControlTemplate>
      </Setter.Value>
    </Setter>
  </Style>
</ResourceDictionary>
"""


def bar_resources():
    """Parsed ResourceDictionary with the palette keys resolved into it.

    The palette keys are injected as real resources rather than left to
    DynamicResource lookup, so the templates render correctly whether or not
    a pyRevit-themed Application is present.

    Returns None if parsing fails, in which case the caller should fall back
    to plain code-built styling.
    """
    try:
        from System.Windows.Markup import XamlReader
        from System.IO import StringReader
        from System.Xml import XmlReader
        rd = XamlReader.Load(XmlReader.Create(StringReader(_BAR_XAML)))
    except Exception:
        return None

    try:
        rd["pyRevitDarkBrush"] = brush("pyRevitDarkBrush", DARK_FALLBACK)
        rd["pyRevitAccentBrush"] = brush("pyRevitAccentBrush", ACCENT_FALLBACK)
        rd["pyRevitAccentColor"] = color("pyRevitAccentColor",
                                         ACCENT_COLOR_FALLBACK)
    except Exception:
        pass
    return rd
