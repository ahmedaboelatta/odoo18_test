$xmlFiles = Get-ChildItem -Path "D:\Alezdhar Company\OneDrive\Documents\GitHub\odoo18_test\bird_connector" -Recurse -Filter *.xml
$entities = @('amp', 'lt', 'gt', 'quot', 'apos')
$issues = @()

foreach ($file in $xmlFiles) {
    $rel = $file.FullName.Substring("D:\Alezdhar Company\OneDrive\Documents\GitHub\odoo18_test\".Length)
    $lines = Get-Content -Path $file.FullName
    $lineno = 0
    foreach ($line in $lines) {
        $lineno++
        $stripped = $line.Trim()
        
        # Check for unescaped ampersands
        if ($stripped -match '&') {
            $foundBadAmp = $false
            $matches = [regex]::Matches($stripped, '&([#A-Za-z0-9]+);?')
            foreach ($m in $matches) {
                $name = $m.Groups[1].Value
                $full = $m.Value
                if ($entities -notcontains $name -and -not $full.EndsWith(';')) {
                    $foundBadAmp = $true
                    break
                }
            }
            if ($foundBadAmp) {
                $issues += "$rel`:$lineno`: Unescaped ampersand: $stripped"
            }
        }
        
        # Check for missing quotes in attributes
        if ($stripped -match '<[A-Za-z][^>]*\s[A-Za-z-]+=([^"''\s>]*)') {
            if (-not ($stripped -match '<[A-Za-z][^>]*\s[A-Za-z-]+="[^"]*"') -and -not ($stripped -match "<[A-Za-z][^>]*\s[A-Za-z-]+='[^']*'")) {
                $issues += "$rel`:$lineno`: Possible missing quotes in attribute: $stripped"
            }
        }
        
        # Check for invalid control characters
        if ($stripped -match '[\x00-\x08\x0b\x0c\x0e-\x1f]') {
            $ctrl = [regex]::Matches($stripped, '[\x00-\x08\x0b\x0c\x0e-\x1f]')
            $ctrlRepr = ($ctrl | ForEach-Object { $_.Value }) -join ''
            $issues += "$rel`:$lineno`: Invalid control characters found in line: $stripped"
        }
    }
    
    # Check XML well-formedness
    try {
        [xml]$xml = Get-Content -Path $file.FullName
    } catch {
        $issues += "$rel`: XML Parse Error: $($_.Exception.Message)"
    }
}

foreach ($issue in $issues) {
    Write-Output $issue
}
