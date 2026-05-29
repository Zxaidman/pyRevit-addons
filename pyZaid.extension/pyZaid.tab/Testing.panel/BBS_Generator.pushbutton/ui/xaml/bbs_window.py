# -*- coding: utf-8 -*-
"""
ui/xaml/bbs_window.py
Full XAML string for the BBS Generator main window & the Parameter Editor Popup.
"""

PARAM_EDITOR_XAML = r'''
<Window xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation"
        xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml"
        Title="Edit Parameters" Height="420" Width="360"
        WindowStartupLocation="CenterOwner" Background="#F5F5F5" FontFamily="Segoe UI" FontSize="12">
    <Grid Margin="12">
        <Grid.RowDefinitions>
            <RowDefinition Height="Auto"/>
            <RowDefinition Height="Auto"/>
            <RowDefinition Height="*"/>
            <RowDefinition Height="Auto"/>
        </Grid.RowDefinitions>
        
        <TextBlock Grid.Row="0" Text="Select or type a parameter name:" FontWeight="SemiBold" Foreground="#2C3E50" Margin="0,0,0,4"/>
        <Grid Grid.Row="1" Margin="0,0,0,10">
            <Grid.ColumnDefinitions><ColumnDefinition Width="*"/><ColumnDefinition Width="Auto"/></Grid.ColumnDefinitions>
            <ComboBox x:Name="cb_available" Grid.Column="0" IsEditable="True" Height="26" Margin="0,0,6,0"/>
            <Button x:Name="btn_add" Grid.Column="1" Content="Add ➕" Background="#3498DB" Foreground="White" BorderThickness="0" Width="60" Cursor="Hand"/>
        </Grid>
        
        <Grid Grid.Row="2">
            <Grid.ColumnDefinitions><ColumnDefinition Width="*"/><ColumnDefinition Width="Auto"/></Grid.ColumnDefinitions>
            <ListBox x:Name="lst_params" Grid.Column="0" Margin="0,0,6,0" BorderBrush="#BDC3C7"/>
            <StackPanel Grid.Column="1" VerticalAlignment="Center">
                <Button x:Name="btn_up" Content="▲" Height="30" Width="30" Margin="0,0,0,6" Background="White" BorderBrush="#BDC3C7" Cursor="Hand"/>
                <Button x:Name="btn_down" Content="▼" Height="30" Width="30" Margin="0,0,0,6" Background="White" BorderBrush="#BDC3C7" Cursor="Hand"/>
                <Button x:Name="btn_del" Content="🗑" Height="30" Width="30" Background="#FADBD8" Foreground="#C0392B" BorderBrush="#E74C3C" Cursor="Hand"/>
            </StackPanel>
        </Grid>
        
        <Grid Grid.Row="3" Margin="0,10,0,0">
            <Grid.ColumnDefinitions><ColumnDefinition Width="*"/><ColumnDefinition Width="Auto"/></Grid.ColumnDefinitions>
            <TextBlock Grid.Column="0" Text="Priority: Top to Bottom" Foreground="#7F8C8D" VerticalAlignment="Center"/>
            <Button x:Name="btn_save" Grid.Column="1" Content="Save Changes" Background="#27AE60" Foreground="White" BorderThickness="0" Padding="10,4" Cursor="Hand"/>
        </Grid>
    </Grid>
</Window>
'''

MAIN_XAML = r'''
<Window xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation"
        xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml"
        Title="BBS Generator"
        Height="740" Width="1100"
        MinHeight="750" MinWidth="1000"
        WindowStartupLocation="CenterScreen"
        ResizeMode="CanResize"
        Background="#F5F5F5"
        FontFamily="Segoe UI"
        FontSize="12"
        UseLayoutRounding="True">

  <Window.Resources>
    <SolidColorBrush x:Key="AccentBrush"    Color="#3498DB"/>
    <SolidColorBrush x:Key="SuccessBrush"   Color="#27AE60"/>
    <SolidColorBrush x:Key="DangerBrush"    Color="#E74C3C"/>
    <SolidColorBrush x:Key="DarkTextBrush"  Color="#2C3E50"/>
    <SolidColorBrush x:Key="GrayTextBrush"  Color="#7F8C8D"/>
    <SolidColorBrush x:Key="WhiteBrush"     Color="#FFFFFF"/>
    <SolidColorBrush x:Key="LightBgBrush"   Color="#F5F5F5"/>
    <SolidColorBrush x:Key="BorderBrush"    Color="#BDC3C7"/>
    <SolidColorBrush x:Key="DividerBrush"   Color="#D5D8DC"/>

    <Style x:Key="SectionLabel" TargetType="Label">
      <Setter Property="FontSize" Value="12"/>
      <Setter Property="FontWeight" Value="SemiBold"/>
      <Setter Property="Foreground" Value="{StaticResource DarkTextBrush}"/>
      <Setter Property="BorderBrush" Value="{StaticResource AccentBrush}"/>
      <Setter Property="BorderThickness" Value="0,0,0,2"/>
      <Setter Property="Padding" Value="0,0,0,3"/>
      <Setter Property="Margin" Value="0,8,0,6"/>
    </Style>

    <Style x:Key="ControlBox" TargetType="TextBox">
      <Setter Property="FontSize" Value="12"/>
      <Setter Property="Padding" Value="5,4"/>
      <Setter Property="BorderBrush" Value="{StaticResource BorderBrush}"/>
      <Setter Property="BorderThickness" Value="1"/>
      <Setter Property="Background" Value="{StaticResource WhiteBrush}"/>
      <Setter Property="Foreground" Value="{StaticResource DarkTextBrush}"/>
      <Setter Property="VerticalContentAlignment" Value="Center"/>
    </Style>

    <Style x:Key="ControlCombo" TargetType="ComboBox">
      <Setter Property="FontSize" Value="12"/>
      <Setter Property="Padding" Value="5,4"/>
      <Setter Property="BorderBrush" Value="{StaticResource BorderBrush}"/>
      <Setter Property="BorderThickness" Value="1"/>
      <Setter Property="Background" Value="{StaticResource WhiteBrush}"/>
      <Setter Property="Foreground" Value="{StaticResource DarkTextBrush}"/>
      <Setter Property="VerticalContentAlignment" Value="Center"/>
    </Style>

    <Style x:Key="ActionButton" TargetType="Button">
      <Setter Property="Background" Value="{StaticResource AccentBrush}"/>
      <Setter Property="Foreground" Value="{StaticResource WhiteBrush}"/>
      <Setter Property="FontSize" Value="12"/>
      <Setter Property="FontWeight" Value="SemiBold"/>
      <Setter Property="Padding" Value="10,4"/>
      <Setter Property="BorderThickness" Value="0"/>
      <Setter Property="Cursor" Value="Hand"/>
      <Setter Property="Height" Value="28"/>
      <Setter Property="Template">
        <Setter.Value>
          <ControlTemplate TargetType="Button">
            <Border Background="{TemplateBinding Background}" CornerRadius="4">
              <ContentPresenter HorizontalAlignment="Center" VerticalAlignment="Center"/>
            </Border>
            <ControlTemplate.Triggers>
              <Trigger Property="IsMouseOver" Value="True">
                <Setter Property="Background" Value="#2980B9"/>
              </Trigger>
            </ControlTemplate.Triggers>
          </ControlTemplate>
        </Setter.Value>
      </Setter>
    </Style>

    <Style x:Key="SecondaryBtn" TargetType="Button">
      <Setter Property="Background" Value="{StaticResource WhiteBrush}"/>
      <Setter Property="Foreground" Value="{StaticResource AccentBrush}"/>
      <Setter Property="FontSize" Value="12"/>
      <Setter Property="Padding" Value="10,4"/>
      <Setter Property="BorderThickness" Value="1.5"/>
      <Setter Property="BorderBrush" Value="{StaticResource AccentBrush}"/>
      <Setter Property="Cursor" Value="Hand"/>
      <Setter Property="Height" Value="28"/>
      <Setter Property="Template">
        <Setter.Value>
          <ControlTemplate TargetType="Button">
            <Border Background="{TemplateBinding Background}" CornerRadius="4" BorderThickness="{TemplateBinding BorderThickness}" BorderBrush="{TemplateBinding BorderBrush}">
              <ContentPresenter HorizontalAlignment="Center" VerticalAlignment="Center"/>
            </Border>
          </ControlTemplate>
        </Setter.Value>
      </Setter>
    </Style>

    <Style x:Key="StatusText" TargetType="TextBlock">
      <Setter Property="FontSize" Value="11"/>
      <Setter Property="Foreground" Value="{StaticResource GrayTextBrush}"/>
    </Style>

    <Style x:Key="CheckItem" TargetType="CheckBox">
      <Setter Property="Margin" Value="0,3,10,3"/>
      <Setter Property="Cursor" Value="Hand"/>
      <Setter Property="VerticalContentAlignment" Value="Center"/>
    </Style>

    <Style x:Key="RadioItem" TargetType="RadioButton">
      <Setter Property="Margin" Value="0,3,12,3"/>
      <Setter Property="Cursor" Value="Hand"/>
      <Setter Property="VerticalContentAlignment" Value="Center"/>
    </Style>
  </Window.Resources>

  <Grid Margin="10">
    <Grid.RowDefinitions>
      <RowDefinition Height="Auto"/>
      <RowDefinition Height="*"/>
      <RowDefinition Height="Auto"/>
      <RowDefinition Height="Auto"/>
    </Grid.RowDefinitions>

    <Border Grid.Row="0" Background="#2C3E50" Padding="12,8" Margin="0,0,0,10" CornerRadius="4">
      <Grid>
        <Grid.ColumnDefinitions>
          <ColumnDefinition Width="Auto"/>
          <ColumnDefinition Width="*"/>
          <ColumnDefinition Width="Auto"/>
          <ColumnDefinition Width="Auto"/>
        </Grid.ColumnDefinitions>
        <TextBlock Grid.Column="0" Text="BBS Generator" FontSize="16" FontWeight="Bold" Foreground="White" VerticalAlignment="Center"/>
        <TextBlock Grid.Column="2" x:Name="lbl_bar_count" Text="0 bars loaded" FontSize="12" Foreground="#BDC3C7" VerticalAlignment="Center" Margin="0,0,16,0"/>
        <TextBlock Grid.Column="3" x:Name="lbl_standard_badge" Text="IS 2502:2019" FontSize="11" Foreground="#3498DB" FontWeight="SemiBold" VerticalAlignment="Center" Background="#1A2A3A" Padding="8,2" />
      </Grid>
    </Border>

    <Grid Grid.Row="1">
      <Grid.ColumnDefinitions>
        <ColumnDefinition Width="2.8*" MinWidth="380"/>
        <ColumnDefinition Width="5"/>
        <ColumnDefinition Width="3*" MinWidth="340"/>
      </Grid.ColumnDefinitions>

      <TabControl x:Name="main_tabs" Grid.Column="0" Background="White" BorderBrush="{StaticResource BorderBrush}" BorderThickness="1">

        <!-- ── TAB 1: SETTINGS ─────────────────────────────────────────── -->
        <TabItem Header=" ⚙ Settings ">
          <ScrollViewer VerticalScrollBarVisibility="Auto">
            <StackPanel Margin="12">
              
              <Label Content="Standard:" Style="{StaticResource SectionLabel}"/>
              <ComboBox x:Name="cb_standard" Style="{StaticResource ControlCombo}" Height="28" Margin="0,0,0,12"/>

              <Label Content="Custom Parameters Mapping (Priority Left-to-Right):" Style="{StaticResource SectionLabel}"/>
              <Grid Margin="0,0,0,12">
                <Grid.ColumnDefinitions><ColumnDefinition Width="110"/><ColumnDefinition Width="*"/><ColumnDefinition Width="Auto"/></Grid.ColumnDefinitions>
                <Grid.RowDefinitions>
                  <RowDefinition Height="Auto"/>
                  <RowDefinition Height="Auto"/>
                  <RowDefinition Height="Auto"/>
                  <RowDefinition Height="Auto"/>
                  <RowDefinition Height="Auto"/>
                  <RowDefinition Height="Auto"/>
                  <RowDefinition Height="Auto"/>
                  <RowDefinition Height="Auto"/>
                </Grid.RowDefinitions>
                
                <TextBlock Grid.Row="0" Grid.Column="0" Text="Bar Mark:" VerticalAlignment="Center" Foreground="{StaticResource DarkTextBrush}"/>
                <TextBox   Grid.Row="0" Grid.Column="1" x:Name="tb_param_mark" Style="{StaticResource ControlBox}" Height="26" Margin="0,2,6,2" IsReadOnly="True" Background="#F8F9F9"/>
                <Button    Grid.Row="0" Grid.Column="2" x:Name="btn_edit_mark" Content="Edit ✎" Style="{StaticResource SecondaryBtn}" Width="50" Height="26"/>

                <TextBlock Grid.Row="1" Grid.Column="0" Text="Bar Type:" VerticalAlignment="Center" Foreground="{StaticResource DarkTextBrush}"/>
                <TextBox   Grid.Row="1" Grid.Column="1" x:Name="tb_param_type" Style="{StaticResource ControlBox}" Height="26" Margin="0,2,6,2" IsReadOnly="True" Background="#F8F9F9"/>
                <Button    Grid.Row="1" Grid.Column="2" x:Name="btn_edit_type" Content="Edit ✎" Style="{StaticResource SecondaryBtn}" Width="50" Height="26"/>
                
                <TextBlock Grid.Row="2" Grid.Column="0" Text="Level:" VerticalAlignment="Center" Foreground="{StaticResource DarkTextBrush}"/>
                <TextBox   Grid.Row="2" Grid.Column="1" x:Name="tb_param_level" Style="{StaticResource ControlBox}" Height="26" Margin="0,2,6,2" IsReadOnly="True" Background="#F8F9F9"/>
                <Button    Grid.Row="2" Grid.Column="2" x:Name="btn_edit_level" Content="Edit ✎" Style="{StaticResource SecondaryBtn}" Width="50" Height="26"/>
                
                <TextBlock Grid.Row="3" Grid.Column="0" Text="Length:" VerticalAlignment="Center" Foreground="{StaticResource DarkTextBrush}"/>
                <TextBox   Grid.Row="3" Grid.Column="1" x:Name="tb_param_length" Style="{StaticResource ControlBox}" Height="26" Margin="0,2,6,2" IsReadOnly="True" Background="#F8F9F9"/>
                <Button    Grid.Row="3" Grid.Column="2" x:Name="btn_edit_length" Content="Edit ✎" Style="{StaticResource SecondaryBtn}" Width="50" Height="26"/>
                
                <TextBlock Grid.Row="4" Grid.Column="0" Text="Quantity:" VerticalAlignment="Center" Foreground="{StaticResource DarkTextBrush}"/>
                <TextBox   Grid.Row="4" Grid.Column="1" x:Name="tb_param_qty" Style="{StaticResource ControlBox}" Height="26" Margin="0,2,6,2" IsReadOnly="True" Background="#F8F9F9"/>
                <Button    Grid.Row="4" Grid.Column="2" x:Name="btn_edit_qty" Content="Edit ✎" Style="{StaticResource SecondaryBtn}" Width="50" Height="26"/>

                <TextBlock Grid.Row="5" Grid.Column="0" Text="Shape Code:" VerticalAlignment="Center" Foreground="{StaticResource DarkTextBrush}"/>
                <TextBox   Grid.Row="5" Grid.Column="1" x:Name="tb_param_shape" Style="{StaticResource ControlBox}" Height="26" Margin="0,2,6,2" IsReadOnly="True" Background="#F8F9F9"/>
                <Button    Grid.Row="5" Grid.Column="2" x:Name="btn_edit_shape" Content="Edit ✎" Style="{StaticResource SecondaryBtn}" Width="50" Height="26"/>

                <TextBlock Grid.Row="6" Grid.Column="0" Text="Member Type:" VerticalAlignment="Center" Foreground="{StaticResource DarkTextBrush}"/>
                <TextBox   Grid.Row="6" Grid.Column="1" x:Name="tb_param_member" Style="{StaticResource ControlBox}" Height="26" Margin="0,2,6,2" IsReadOnly="True" Background="#F8F9F9"/>
                <Button    Grid.Row="6" Grid.Column="2" x:Name="btn_edit_member" Content="Edit ✎" Style="{StaticResource SecondaryBtn}" Width="50" Height="26"/>

                <TextBlock Grid.Row="7" Grid.Column="0" Text="Bar Details:" VerticalAlignment="Center" Foreground="{StaticResource DarkTextBrush}"/>
                <TextBox   Grid.Row="7" Grid.Column="1" x:Name="tb_param_detail" Style="{StaticResource ControlBox}" Height="26" Margin="0,2,6,2" IsReadOnly="True" Background="#F8F9F9"/>
                <Button    Grid.Row="7" Grid.Column="2" x:Name="btn_edit_detail" Content="Edit ✎" Style="{StaticResource SecondaryBtn}" Width="50" Height="26"/>
              </Grid>

              <Label Content="Output Organisation:" Style="{StaticResource SectionLabel}"/>
              <StackPanel Orientation="Horizontal" Margin="0,0,0,4">
                <RadioButton x:Name="rb_org_floor"  Content="Per Floor Level" GroupName="org" IsChecked="True" Style="{StaticResource RadioItem}"/>
                <RadioButton x:Name="rb_org_elem"   Content="Per Element"     GroupName="org" Style="{StaticResource RadioItem}"/>
                <RadioButton x:Name="rb_org_both"   Content="Both"            GroupName="org" Style="{StaticResource RadioItem}"/>
              </StackPanel>

              <Label Content="Excel Sheets:" Style="{StaticResource SectionLabel}"/>
              <CheckBox x:Name="chk_bbs_sheet"    Content="BBS Sheet"         IsChecked="True" Style="{StaticResource CheckItem}"/>
              <CheckBox x:Name="chk_calc_sheet"   Content="Calculation Sheet" IsChecked="True" Style="{StaticResource CheckItem}"/>
              <CheckBox x:Name="chk_summary_sheet" Content="Summary Sheet"    IsChecked="True" Style="{StaticResource CheckItem}"/>

              <Label Content="Columns:" Style="{StaticResource SectionLabel}"/>
              <CheckBox x:Name="chk_unit_weight"  Content="Show Unit Weight column (kg/m)" IsChecked="False" Style="{StaticResource CheckItem}"/>

              <Label Content="Export Options:" Style="{StaticResource SectionLabel}"/>
              <CheckBox x:Name="chk_pdf"          Content="Export PDF alongside Excel"     IsChecked="False" Style="{StaticResource CheckItem}"/>

              <Label Content="Revision Tracking:" Style="{StaticResource SectionLabel}"/>
              <CheckBox x:Name="chk_revision"     Content="Enable revision comparison"     IsChecked="True"  Style="{StaticResource CheckItem}"/>
              <Grid Margin="0,6,0,0">
                <Grid.ColumnDefinitions><ColumnDefinition Width="*"/><ColumnDefinition Width="Auto"/></Grid.ColumnDefinitions>
                <TextBox x:Name="tb_prev_bbs" Grid.Column="0" Style="{StaticResource ControlBox}" IsReadOnly="True" Height="28" Text="" Margin="0,0,6,0"/>
                <Button x:Name="btn_browse_prev" Grid.Column="1" Content="Browse…" Style="{StaticResource SecondaryBtn}" Width="72"/>
              </Grid>
              <TextBlock x:Name="lbl_rev_status" Text="" Style="{StaticResource StatusText}" Margin="0,4,0,0"/>

              <Label Content="Project Info:" Style="{StaticResource SectionLabel}"/>
              <Grid Margin="0,0,0,4">
                <Grid.ColumnDefinitions><ColumnDefinition Width="100"/><ColumnDefinition Width="*"/></Grid.ColumnDefinitions>
                <Grid.RowDefinitions>
                  <RowDefinition Height="Auto"/>
                  <RowDefinition Height="Auto"/>
                  <RowDefinition Height="Auto"/>
                  <RowDefinition Height="Auto"/>
                </Grid.RowDefinitions>
                <TextBlock Grid.Row="0" Grid.Column="0" Text="Project Name:" VerticalAlignment="Center" Foreground="{StaticResource DarkTextBrush}"/>
                <TextBox   Grid.Row="0" Grid.Column="1" x:Name="tb_project_name" Style="{StaticResource ControlBox}" Height="26" Margin="0,2"/>
                <TextBlock Grid.Row="1" Grid.Column="0" Text="Drawing No:" VerticalAlignment="Center" Foreground="{StaticResource DarkTextBrush}"/>
                <TextBox   Grid.Row="1" Grid.Column="1" x:Name="tb_drawing_no"   Style="{StaticResource ControlBox}" Height="26" Margin="0,2"/>
                <TextBlock Grid.Row="2" Grid.Column="0" Text="Prepared By:" VerticalAlignment="Center" Foreground="{StaticResource DarkTextBrush}"/>
                <TextBox   Grid.Row="2" Grid.Column="1" x:Name="tb_prepared_by"  Style="{StaticResource ControlBox}" Height="26" Margin="0,2"/>
                <TextBlock Grid.Row="3" Grid.Column="0" Text="Revision:" VerticalAlignment="Center" Foreground="{StaticResource DarkTextBrush}"/>
                <TextBox   Grid.Row="3" Grid.Column="1" x:Name="tb_revision"     Style="{StaticResource ControlBox}" Height="26" Margin="0,2" Text="A"/>
              </Grid>

              <Button x:Name="btn_save_settings" Content="Save Settings" Style="{StaticResource SecondaryBtn}" Width="120" HorizontalAlignment="Left" Margin="0,10,0,0"/>
            </StackPanel>
          </ScrollViewer>
        </TabItem>

        <!-- ── TAB 2: SCOPE ───────────────────────────────────────────── -->
        <TabItem Header=" 🔍 Scope ">
          <Grid Margin="12">
            <Grid.RowDefinitions>
              <RowDefinition Height="Auto"/>
              <RowDefinition Height="Auto"/>
              <RowDefinition Height="Auto"/>
              <RowDefinition Height="Auto"/>
              <RowDefinition Height="*"/>
              <RowDefinition Height="Auto"/>
              <RowDefinition Height="Auto"/>
              <RowDefinition Height="Auto"/>
            </Grid.RowDefinitions>

            <Label Grid.Row="0" Content="Source:" Style="{StaticResource SectionLabel}"/>
            <StackPanel Grid.Row="1" Orientation="Horizontal" Margin="0,0,0,8">
              <RadioButton x:Name="rb_scope_model"     Content="Whole Model"   GroupName="scope" IsChecked="True" Style="{StaticResource RadioItem}"/>
              <RadioButton x:Name="rb_scope_view"      Content="Active View"   GroupName="scope" Style="{StaticResource RadioItem}"/>
              <RadioButton x:Name="rb_scope_selection" Content="Selection"     GroupName="scope" Style="{StaticResource RadioItem}"/>
            </StackPanel>

            <Label Grid.Row="2" Content="Filter by Level:" Style="{StaticResource SectionLabel}"/>
            <ScrollViewer Grid.Row="3" Height="100" Margin="0,0,0,8" VerticalScrollBarVisibility="Auto" Background="White" BorderBrush="{StaticResource BorderBrush}" BorderThickness="1">
              <WrapPanel x:Name="level_filter_panel" Orientation="Horizontal" Margin="4"/>
            </ScrollViewer>

            <Label Grid.Row="4" Content="Filter by Member Type:" Style="{StaticResource SectionLabel}"/>
            <ScrollViewer Grid.Row="5" Height="80" Margin="0,0,0,8" VerticalScrollBarVisibility="Auto" Background="White" BorderBrush="{StaticResource BorderBrush}" BorderThickness="1">
              <WrapPanel x:Name="member_filter_panel" Orientation="Horizontal" Margin="4"/>
            </ScrollViewer>

            <Label Grid.Row="6" Content="Filter by Diameter:" Style="{StaticResource SectionLabel}"/>
            <WrapPanel Grid.Row="7" x:Name="dia_filter_panel" Orientation="Horizontal" Margin="0,0,0,8"/>
          </Grid>
        </TabItem>

        <!-- ── TAB 3: PREVIEW ────────────────────────────────────────── -->
        <TabItem Header=" 👁 Preview ">
          <Grid Margin="12">
            <Grid.RowDefinitions>
              <RowDefinition Height="Auto"/>
              <RowDefinition Height="Auto"/>
              <RowDefinition Height="*"/>
              <RowDefinition Height="Auto"/>
            </Grid.RowDefinitions>
            <Label Grid.Row="0" Content="Bar Records:" Style="{StaticResource SectionLabel}"/>
            <WrapPanel Grid.Row="1" Margin="0,0,0,8">
              <Border Background="#EBF5FB" BorderBrush="#3498DB" BorderThickness="1" CornerRadius="4" Padding="8,3" Margin="0,0,8,0">
                <TextBlock x:Name="badge_total_bars" Text="0 bars" FontWeight="SemiBold" Foreground="#1A5276"/>
              </Border>
              <Border Background="#EAFAF1" BorderBrush="#27AE60" BorderThickness="1" CornerRadius="4" Padding="8,3" Margin="0,0,8,0">
                <TextBlock x:Name="badge_total_weight" Text="0.000 kg" FontWeight="SemiBold" Foreground="#1E8449"/>
              </Border>
              <Border Background="#FEF9E7" BorderBrush="#F39C12" BorderThickness="1" CornerRadius="4" Padding="8,3" Margin="0,0,8,0">
                <TextBlock x:Name="badge_warnings" Text="0 warnings" FontWeight="SemiBold" Foreground="#9A7D0A"/>
              </Border>
            </WrapPanel>
            <DataGrid Grid.Row="2" x:Name="preview_grid" AutoGenerateColumns="False" IsReadOnly="True" HeadersVisibility="Column" GridLinesVisibility="Horizontal" AlternatingRowBackground="#F8F9F9" Background="White" BorderBrush="{StaticResource BorderBrush}" BorderThickness="1" FontSize="11" RowHeight="22" Margin="0,0,0,8">
              <DataGrid.Columns>
                <DataGridTextColumn Header="Mark"   Binding="{Binding bar_mark}"          Width="55"/>
                <DataGridTextColumn Header="Level"  Binding="{Binding floor_level}"       Width="70"/>
                <DataGridTextColumn Header="Member" Binding="{Binding member_name}"       Width="52"/>
                <DataGridTextColumn Header="Dia"    Binding="{Binding diameter_mm}"       Width="33"/>
                <DataGridTextColumn Header="Shape"  Binding="{Binding shape_code}"        Width="44"/>
                <DataGridTextColumn Header="A"      Binding="{Binding dim_A}"             Width="40"/>
                <DataGridTextColumn Header="B"      Binding="{Binding dim_B}"             Width="40"/>
                <DataGridTextColumn Header="C"      Binding="{Binding dim_C}"             Width="40"/>
                <DataGridTextColumn Header="No."    Binding="{Binding no_of_bars}"        Width="33"/>
                <DataGridTextColumn Header="Cut.L"  Binding="{Binding cutting_length_mm}" Width="52"/>
                <DataGridTextColumn Header="Wt(kg)" Binding="{Binding total_weight_kg}"   Width="52"/>
              </DataGrid.Columns>
            </DataGrid>
            <Button Grid.Row="3" x:Name="btn_refresh_preview" Content="↻ Refresh Preview" Style="{StaticResource SecondaryBtn}" Width="140" HorizontalAlignment="Left"/>
          </Grid>
        </TabItem>

        <!-- ── TAB 4: EXPORT ──────────────────────────────────────────── -->
        <TabItem Header=" 📤 Export ">
          <ScrollViewer VerticalScrollBarVisibility="Auto">
            <StackPanel Margin="12">
              <Label Content="Output Folder:" Style="{StaticResource SectionLabel}"/>
              <Grid Margin="0,0,0,8">
                <Grid.ColumnDefinitions><ColumnDefinition Width="*"/><ColumnDefinition Width="Auto"/></Grid.ColumnDefinitions>
                <TextBox x:Name="tb_output_folder" Grid.Column="0" Style="{StaticResource ControlBox}" Height="28" Margin="0,0,6,0" IsReadOnly="True"/>
                <Button x:Name="btn_browse_output" Grid.Column="1" Content="Browse…" Style="{StaticResource SecondaryBtn}" Width="72"/>
              </Grid>
              <Label Content="File Name:" Style="{StaticResource SectionLabel}"/>
              <TextBox x:Name="tb_filename" Style="{StaticResource ControlBox}" Height="28" Margin="0,0,0,8"/>
              <Label Content="Revision Diff Summary:" Style="{StaticResource SectionLabel}"/>
              <Border x:Name="rev_diff_border" Background="#F8F9FA" BorderBrush="{StaticResource BorderBrush}" BorderThickness="1" CornerRadius="4" Padding="10,8" Margin="0,0,0,12">
                <StackPanel>
                  <TextBlock x:Name="lbl_diff_new"     Text="New bars:     —" Style="{StaticResource StatusText}"/>
                  <TextBlock x:Name="lbl_diff_changed" Text="Changed bars: —" Style="{StaticResource StatusText}"/>
                  <TextBlock x:Name="lbl_diff_deleted" Text="Deleted bars: —" Style="{StaticResource StatusText}"/>
                  <TextBlock x:Name="lbl_diff_same"    Text="Unchanged:    —" Style="{StaticResource StatusText}"/>
                </StackPanel>
              </Border>
              <Button x:Name="btn_export" Content="Export BBS" Style="{StaticResource ActionButton}" Width="140" HorizontalAlignment="Left" Height="32" FontSize="13"/>
              <TextBlock x:Name="lbl_export_path" Text="" Style="{StaticResource StatusText}" Margin="0,6,0,0" TextWrapping="Wrap" Foreground="#27AE60"/>
              <Label Content="Export Log (Check here for Errors):" Style="{StaticResource SectionLabel}"/>
              <TextBox x:Name="tb_log" Style="{StaticResource ControlBox}" Height="180" IsReadOnly="True" TextWrapping="Wrap" VerticalScrollBarVisibility="Auto" Background="#F8F9FA" FontFamily="Consolas" FontSize="11" Margin="0,0,0,0"/>
            </StackPanel>
          </ScrollViewer>
        </TabItem>
      </TabControl>

      <GridSplitter Grid.Column="1" Width="5" HorizontalAlignment="Center" VerticalAlignment="Stretch" Background="{StaticResource DividerBrush}"/>

      <!-- RIGHT: Live Preview Panel -->
      <Border Grid.Column="2" Background="White" BorderBrush="{StaticResource BorderBrush}" BorderThickness="1" CornerRadius="4" Padding="12" Margin="0,0,0,0">
        <Grid>
          <Grid.RowDefinitions>
            <RowDefinition Height="Auto"/>
            <RowDefinition Height="Auto"/>
            <RowDefinition Height="*"/>
            <RowDefinition Height="Auto"/>
          </Grid.RowDefinitions>
          <Grid Grid.Row="0" Margin="0,0,0,8">
            <Grid.ColumnDefinitions><ColumnDefinition Width="*"/><ColumnDefinition Width="Auto"/></Grid.ColumnDefinitions>
            <TextBlock Grid.Column="0" Text="Live Preview" FontSize="13" FontWeight="SemiBold" Foreground="{StaticResource DarkTextBrush}" VerticalAlignment="Center"/>
            <Button Grid.Column="1" x:Name="btn_load_bars" Content="Load Bars →" Style="{StaticResource ActionButton}" Width="100"/>
          </Grid>
          <WrapPanel Grid.Row="1" Margin="0,0,0,8">
            <Border Background="#EBF5FB" BorderBrush="#3498DB" BorderThickness="1" CornerRadius="3" Padding="6,2" Margin="0,0,6,4">
              <TextBlock x:Name="rp_total_bars" Text="0 bars" FontSize="11" FontWeight="SemiBold" Foreground="#1A5276"/>
            </Border>
            <Border Background="#EAFAF1" BorderBrush="#27AE60" BorderThickness="1" CornerRadius="3" Padding="6,2" Margin="0,0,6,4">
              <TextBlock x:Name="rp_total_weight" Text="0.000 kg" FontSize="11" FontWeight="SemiBold" Foreground="#1E8449"/>
            </Border>
          </WrapPanel>
          <ScrollViewer Grid.Row="2" VerticalScrollBarVisibility="Auto">
            <StackPanel>
              <TextBlock Text="Weight by Diameter:" FontWeight="SemiBold" Foreground="{StaticResource DarkTextBrush}" Margin="0,0,0,6"/>
              <DataGrid x:Name="rp_dia_grid" AutoGenerateColumns="False" IsReadOnly="True" HeadersVisibility="Column" GridLinesVisibility="Horizontal" AlternatingRowBackground="#F8F9F9" Background="White" BorderBrush="{StaticResource BorderBrush}" BorderThickness="1" FontSize="11" RowHeight="20" Margin="0,0,0,12">
                <DataGrid.Columns>
                  <DataGridTextColumn Header="Dia"        Binding="{Binding dia_label}"   Width="50"/>
                  <DataGridTextColumn Header="No. Bars"   Binding="{Binding no_bars}"     Width="70"/>
                  <DataGridTextColumn Header="Length (m)" Binding="{Binding total_len_m}" Width="80"/>
                  <DataGridTextColumn Header="Wt (kg)"    Binding="{Binding total_wt_kg}" Width="80"/>
                </DataGrid.Columns>
              </DataGrid>
              <TextBlock Text="Warnings:" FontWeight="SemiBold" Foreground="{StaticResource DarkTextBrush}" Margin="0,0,0,6"/>
              <ListBox x:Name="rp_warnings" Background="#FFF9F0" BorderBrush="#F39C12" BorderThickness="1" MaxHeight="150" FontSize="11"/>
            </StackPanel>
          </ScrollViewer>
          <StackPanel Grid.Row="3" Margin="0,8,0,0">
            <ProgressBar x:Name="progress_bar" Height="6" Minimum="0" Maximum="100" Value="0" Foreground="{StaticResource AccentBrush}" Background="#E8E8E8" BorderThickness="0" Margin="0,0,0,4"/>
            <TextBlock x:Name="lbl_progress" Text="" Style="{StaticResource StatusText}" TextWrapping="Wrap"/>
          </StackPanel>
        </Grid>
      </Border>
    </Grid>

    <Border Grid.Row="2" Background="#E8E8E8" Padding="10,5" Margin="0,8,0,6" CornerRadius="4">
      <Grid>
        <Grid.ColumnDefinitions><ColumnDefinition Width="Auto"/><ColumnDefinition Width="*"/><ColumnDefinition Width="Auto"/></Grid.ColumnDefinitions>
        <Border x:Name="status_badge" Grid.Column="0" Background="#D5F5E3" BorderBrush="#27AE60" BorderThickness="1" CornerRadius="4" Padding="10,2">
          <TextBlock x:Name="status_text" Text="Ready" FontSize="11" Foreground="#1E8449" FontWeight="SemiBold"/>
        </Border>
        <Border x:Name="error_badge" Grid.Column="0" Background="#FADBD8" BorderBrush="#E74C3C" BorderThickness="1" CornerRadius="4" Padding="10,2" Visibility="Collapsed">
          <TextBlock x:Name="error_text" Text="" FontSize="11" Foreground="#C0392B" FontWeight="SemiBold"/>
        </Border>
        <TextBlock Grid.Column="2" Text="pyZaid | BBS Generator v1.0" Style="{StaticResource StatusText}" VerticalAlignment="Center"/>
      </Grid>
    </Border>

    <Border Grid.Row="3" Background="{StaticResource LightBgBrush}">
      <Grid>
        <Grid.ColumnDefinitions><ColumnDefinition Width="*"/><ColumnDefinition Width="Auto"/></Grid.ColumnDefinitions>
        <TextBlock Grid.Column="0" x:Name="lbl_footer_hint" Text="Select scope → Load Bars → Preview → Export" Style="{StaticResource StatusText}" VerticalAlignment="Center"/>
        <Button Grid.Column="1" x:Name="btn_close" Content="Close" Style="{StaticResource SecondaryBtn}" Width="80" HorizontalAlignment="Right"/>
      </Grid>
    </Border>
  </Grid>
</Window>
'''