const fs = require('fs');
const path = require('path');

const baseDir = 'D:\\Alezdhar Company\\OneDrive\\Documents\\GitHub\\odoo18_test';
const scanDir = path.join(baseDir, 'bird_connector');

function findXmlFiles(dir) {
    let results = [];
    try {
        fs.readdirSync(dir).forEach(file => {
            const filePath = path.join(dir, file);
            const stat = fs.statSync(filePath);
            if (stat.isDirectory()) {
                results = results.concat(findXmlFiles(filePath));
            } else if (file.toLowerCase().endsWith('.xml')) {
                results.push(filePath);
            }
        });
    } catch (e) {}
    return results;
}

const xmlFiles = findXmlFiles(scanDir);
const issues = [];

for (const filePath of xmlFiles) {
    const rel = path.relative(baseDir, filePath);
    let content;
    try {
        content = fs.readFileSync(filePath, 'utf8');
    } catch (e) {
        issues.push(`${rel}: Error reading file: ${e.message}`);
        continue;
    }
    
    const lines = content.split(/\r?\n/);
    
    for (let i = 0; i < lines.length; i++) {
        const line = lines[i];
        const lineno = i + 1;
        const stripped = line.trim();
        
        // 1. Unescaped ampersands
        const ampRegex = /&/g;
        let a;
        while ((a = ampRegex.exec(line)) !== null) {
            const rest = line.substring(a.index);
            const entityMatch = rest.match(/^&([A-Za-z0-9#]+);?/);
            if (!entityMatch) {
                issues.push(`${rel}:${lineno}: Bare '&' not part of entity: ${stripped}`);
                break;
            }
            const name = entityMatch[1];
            const full = entityMatch[0];
            const valid = ['amp','lt','gt','quot','apos'].includes(name) || /^#(\d+|x[0-9A-Fa-f]+)$/i.test(name);
            if (!valid) {
                if (full.endsWith(';')) {
                    issues.push(`${rel}:${lineno}: Non-standard entity reference '${full}': ${stripped}`);
                } else {
                    issues.push(`${rel}:${lineno}: Unescaped ampersand (missing ';'): ${stripped}`);
                }
                break;
            }
            ampRegex.lastIndex = a.index + full.length - 1;
        }
        
        // 2. Unescaped < or > in text content
        const ltRegex = /</g;
        let lt;
        while ((lt = ltRegex.exec(line)) !== null) {
            const rest = line.substring(lt.index);
            if (rest.startsWith('<!--')) {
                const endComment = rest.indexOf('-->');
                if (endComment > -1) {
                    ltRegex.lastIndex = lt.index + endComment + 2;
                    continue;
                }
            }
            if (rest.startsWith('<![CDATA[')) {
                const endCdata = rest.indexOf(']]>');
                if (endCdata > -1) {
                    ltRegex.lastIndex = lt.index + endCdata + 2;
                    continue;
                }
            }
            if (rest.startsWith('<?') || rest.startsWith('<!')) {
                const endPi = rest.indexOf('>');
                if (endPi > -1) {
                    ltRegex.lastIndex = lt.index + endPi + 1;
                    continue;
                }
            }
            const tagMatch = rest.match(/^<\/?[A-Za-z_][A-Za-z0-9_.:-]*(?:\s[^>]*?)?>/);
            if (tagMatch) {
                ltRegex.lastIndex = lt.index + tagMatch[0].length;
                continue;
            }
            issues.push(`${rel}:${lineno}: Unescaped '<': ${stripped}`);
            break;
        }
        
        // 3. Missing quotes in attributes
        const tagMatch = line.match(/<[^>]*>/);
        if (tagMatch) {
            const tag = tagMatch[0];
            // Look for attributes that are not quoted properly
            // Pattern: attr=value where value is not wrapped in quotes and contains special chars or space
            const unquotedRegex = /<[^>]*\b([A-Za-z-]+)\s*=\s*(?:"[^"]*"|'[^']*'|[^"'\s>]+)/g;
            // Actually let's look for = followed by something that isn't quoted
            const attrPattern = /\b[A-Za-z-]+\s*=\s*(?:"[^"]*"|'[^']*'|[^"'\s>]+)/g;
            let m;
            while ((m = attrPattern.exec(tag)) !== null) {
                const fullAttr = m[0];
                const eqIdx = fullAttr.indexOf('=');
                if (eqIdx > -1) {
                    const value = fullAttr.substring(eqIdx + 1).trim();
                    if (!value.startsWith('"') && !value.startsWith("'")) {
                        if (/[\s"'<>`=]/.test(value)) {
                            issues.push(`${rel}:${lineno}: Unquoted attribute value with special chars: ${stripped}`);
                            break;
                        }
                    }
                }
            }
        }
        
        // 4. Boolean attributes without values (e.g., readonly, disabled, checked)
        // In XML, attributes must have values, but HTML allows boolean attrs
        if (tagMatch) {
            const tag = tagMatch[0];
            const boolAttrRegex = /\s([A-Za-z-]+)(?=\s|>)(?=\s*\/?>)/g;
            // Actually we need to find attributes that are present but have no =value
            // Pattern: space + word that is followed by space or > or />
            const attrNamesOnly = tag.match(/\s[A-Za-z][A-Za-z0-9-]*(?=[\s/>])/g);
            if (attrNamesOnly) {
                for (const attr of attrNamesOnly) {
                    const attrName = attr.trim();
                    // Check if this attribute is followed by = (meaning it has a value)
                    const idx = tag.indexOf(attr);
                    if (idx > -1) {
                        const afterAttr = tag.substring(idx + attr.length);
                        if (!afterAttr.match(/^\s*=/)) {
                            // This attribute has no value - flag it
                            issues.push(`${rel}:${lineno}: Boolean attribute without value '${attrName}': ${stripped}`);
                            break;
                        }
                    }
                }
            }
        }
        
        // 5. Invalid control characters
        const ctrlRegex = /[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]/g;
        let ctrl;
        let foundCtrl = false;
        while ((ctrl = ctrlRegex.exec(line)) !== null) {
            issues.push(`${rel}:${lineno}: Invalid control character: ${JSON.stringify(ctrl[0])} in line: ${stripped}`);
            foundCtrl = true;
            break;
        }
    }
    
    // Global tag balance check
    const globalTagRegex = /<\/?([A-Za-z_][A-Za-z0-9_.:-]*)[^>]*>/g;
    const stack = [];
    let match;
    
    while ((match = globalTagRegex.exec(content)) !== null) {
        const fullTag = match[0];
        const tagName = match[1];
        const isSelfClosing = fullTag.endsWith('/>');
        const isClosing = fullTag.startsWith('</');
        const lineNum = content.substring(0, match.index).split(/\r?\n/).length;
        
        if (tagName === '!--' || tagName === '!DOCTYPE' || tagName === '?xml') {
            continue;
        }
        
        if (isClosing) {
            if (stack.length > 0 && stack[stack.length - 1] === tagName) {
                stack.pop();
            } else {
                issues.push(`${rel}:${lineNum}: Unmatched closing tag </${tagName}>`);
            }
        } else if (!isSelfClosing) {
            stack.push(tagName);
        }
    }
    
    if (stack.length > 0) {
        const lineNum = content.split(/\r?\n/).length;
        issues.push(`${rel}:${lineNum}: Unclosed tag(s): ${stack.join(', ')}`);
    }
}

issues.forEach(issue => console.log(issue));

if (issues.length === 0) {
    console.log('No XML issues found.');
}
