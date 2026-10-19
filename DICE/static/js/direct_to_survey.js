console.log('redirect ready')

let link = js_vars.link
console.log(link)

setTimeout(Redirect, js_vars.redirect_delay);
function Redirect()
{
    window.location=link;
}
